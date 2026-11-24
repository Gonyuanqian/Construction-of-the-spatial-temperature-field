package com.tfield.gateway.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class SecurityConfiguration {
    @Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(12); }
    @Bean ApplicationRunner bootstrapAdministrator(AccountService accounts,Environment env) {
        return args->accounts.bootstrap(env.getProperty("TFIELD_BOOTSTRAP_ADMIN_USERNAME"),env.getProperty("TFIELD_BOOTSTRAP_ADMIN_PASSWORD"));
    }
    public static String bearer(HttpServletRequest request) {
        String value=request.getHeader("Authorization");
        return value!=null && value.startsWith("Bearer ")?value.substring(7):null;
    }
    @Bean SecurityFilterChain security(HttpSecurity http,AccountService accounts,ObjectMapper mapper) throws Exception {
        OncePerRequestFilter tokens=new OncePerRequestFilter() {
            @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain) throws ServletException,IOException {
                String token=bearer(request);
                try {
                    if(token!=null) accounts.authenticate(token).ifPresent(a->SecurityContextHolder.getContext().setAuthentication(
                        new UsernamePasswordAuthenticationToken(a,null,List.of(new SimpleGrantedAuthority("ROLE_"+a.role())))));
                    chain.doFilter(request,response);
                } catch(org.springframework.dao.DataAccessException e) {
                    response.setStatus(503); response.setContentType("application/json;charset=UTF-8");
                    mapper.writeValue(response.getOutputStream(),Map.of("detail","账号服务暂不可用。"));
                } finally { SecurityContextHolder.clearContext(); }
            }
        };
        return http.cors(c->{}).csrf(c->c.disable()) // Bearer header only; no cookie authentication.
            .sessionManagement(c->c.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c->c.disable()).formLogin(c->c.disable()).httpBasic(c->c.disable())
            .exceptionHandling(c->c.authenticationEntryPoint((req,res,e)->{
                res.setStatus(401); res.setContentType("application/json;charset=UTF-8"); mapper.writeValue(res.getOutputStream(),Map.of("detail","请先登录。"));
            }).accessDeniedHandler((req,res,e)->{
                res.setStatus(403); res.setContentType("application/json;charset=UTF-8"); mapper.writeValue(res.getOutputStream(),Map.of("detail","当前账号无权执行此操作。"));
            }))
            .authorizeHttpRequests(c->c.dispatcherTypeMatchers(DispatcherType.ERROR,DispatcherType.ASYNC).permitAll()
                .requestMatchers(HttpMethod.OPTIONS,"/**").permitAll()
                .requestMatchers(HttpMethod.POST,"/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET,"/api/health").permitAll()
                .requestMatchers("/api/auth/**").authenticated()
                .requestMatchers("/api/admin/**","/ops/info").hasRole("ADMIN")
                .requestMatchers("/api/user/**").hasAnyRole("USER","ADMIN")
                .requestMatchers("/api/live/**").hasAnyRole("USER","ADMIN")
                .requestMatchers("/api/assistant/**").hasAnyRole("USER","ADMIN")
                .requestMatchers("/api/**").hasRole("ADMIN")
                .requestMatchers("/ops/health","/internal/v1/model-store/**").permitAll()
                .anyRequest().permitAll())
            .addFilterBefore(tokens,UsernamePasswordAuthenticationFilter.class).build();
    }
}
