package com.tfield.gateway.api;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class FrontendController {
    @GetMapping("/")
    public String index() {
        // ResourceHttpRequestHandler 会拒绝空资源路径，首页显式转给静态入口。
        return "forward:/index.html";
    }
}
