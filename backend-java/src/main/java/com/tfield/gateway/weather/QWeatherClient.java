package com.tfield.gateway.weather;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URI;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import com.tfield.gateway.security.AccountService;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import java.util.zip.GZIPInputStream;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/** Authenticated coordinate query. No model inference, database mutation or scheduled polling. */
@Service
public class QWeatherClient {
    record Reply(int status,String body) {}
    interface Transport { Reply get(URI uri,String key) throws Exception; }
    record Entry(Instant expires,Map<String,Object> data,DatasetApiException error) {}
    record Budget(Instant since,int count) {}
    record SolarSample(Instant time,Instant fetched,JsonNode row,String tag,List<String> credits) {}
    private final Map<String,java.util.NavigableMap<Instant,SolarSample>> solarSeries=new LinkedHashMap<>(32,.75f,true) {
        @Override protected boolean removeEldestEntry(Map.Entry<String,java.util.NavigableMap<Instant,SolarSample>> eldest) { return size()>256; }
    };
    record Ticket(String owner,Instant expires,JsonNode snapshot) {}
    private final Map<String,Ticket> tickets=new LinkedHashMap<>() {
        @Override protected boolean removeEldestEntry(Map.Entry<String,Ticket> eldest) { return size()>4096; }
    };
    private final ObjectMapper mapper;
    private final RegionCatalog regions;
    private final WeatherLightNormalizer light;
    private final Clock clock;
    private final Transport transport;
    private final long ttlSeconds;
    private final long failureSeconds;
    private final int requestsPerMinute;
    private final String host;
    private final String apiKey;
    private final ReentrantLock[] locks=new ReentrantLock[32];
    private final Map<String,Entry> cache=new LinkedHashMap<>(32,.75f,true) {
        @Override protected boolean removeEldestEntry(Map.Entry<String,Entry> eldest) { return size()>256; }
    };
    private final Map<String,Budget> budgets=new LinkedHashMap<>(32,.75f,true) {
        @Override protected boolean removeEldestEntry(Map.Entry<String,Budget> eldest) { return size()>1024; }
    };

    @Autowired
    public QWeatherClient(ObjectMapper mapper,RegionCatalog regions,WeatherLightNormalizer light,
            @Value("${tfield.qweather.config-file:}") String config,
            @Value("${tfield.qweather.cache-ttl-seconds:900}") long ttl,
            @Value("${tfield.qweather.failure-ttl-seconds:60}") long failure,
            @Value("${tfield.qweather.requests-per-minute:6}") int rate) {
        this(mapper,regions,light,config,ttl,failure,rate,Clock.systemUTC(),new HttpTransport());
    }

    QWeatherClient(ObjectMapper mapper,RegionCatalog regions,WeatherLightNormalizer light,String config,
            long ttl,long failure,int rate,Clock clock,Transport transport) {
        this.mapper=mapper;this.regions=regions;this.light=light;this.clock=clock;this.transport=transport;
        if(ttl<60 || ttl>3600 || failure<1 || failure>900 || rate<1 || rate>60)
            throw new IllegalArgumentException("气象缓存和请求频率配置超出有效范围。");
        ttlSeconds=ttl;failureSeconds=failure;requestsPerMinute=rate;
        String configuredHost="",configuredKey="";
        try {
            if(!config.isBlank() && Files.isRegularFile(Path.of(config))) {
                if(Files.size(Path.of(config))>65536) throw new IllegalArgumentException();
                JsonNode settings=mapper.readTree(Files.readString(Path.of(config),StandardCharsets.UTF_8));
                configuredHost=settings.path("api_host").asText("").trim().toLowerCase(Locale.ROOT);
                configuredKey=settings.path("api_key").asText("").trim();
                if(!configuredHost.matches("(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+qweatherapi\\.com")
                        || configuredKey.isBlank() || configuredKey.length()>512 || !configuredKey.chars().allMatch(c->c>=33&&c<=126))
                    throw new IllegalArgumentException();
            }
        } catch(Exception e) { throw new IllegalArgumentException("和风天气本机配置无效，请核对 API Host 和 API KEY。"); }
        host=configuredHost;apiKey=configuredKey;
        for(int i=0;i<locks.length;i++) locks[i]=new ReentrantLock();
    }

    public Map<String,Object> query(Account actor,Map<String,Object> body) {
        return queryWithMode(actor,body,false);
    }
    public Map<String,Object> querySingle(Account actor,Map<String,Object> body) {
        return queryWithMode(actor,body,true);
    }
    private Map<String,Object> queryWithMode(Account actor,Map<String,Object> body,boolean single) {
        if(!body.keySet().equals(Set.of("location","latitude","longitude","coordinate_system")))
            throw new DatasetApiException(422,"请提供监测地区、latitude、longitude 和 coordinate_system，不接受自定义气象源地址。");
        var location=regions.validate(body.get("location"));
        if(!"GCJ-02".equals(body.get("coordinate_system"))) throw new DatasetApiException(422,"吉林省监测地点需要 GCJ-02 坐标。");
        double latitude=coordinate(body,"latitude",-90,90),longitude=coordinate(body,"longitude",-180,180);
        // The current product and region picker cover Jilin only. Reject unrelated global queries.
        if(latitude<40 || latitude>47 || longitude<121 || longitude>132) throw new DatasetApiException(422,"当前气象查询仅支持吉林省监测范围。");
        if(host.isEmpty()) throw new DatasetApiException(503,"气象源尚未配置，请联系管理员。");
        String lat=rounded(latitude),lon=rounded(longitude),key=lat+","+lon;
        ReentrantLock lock=locks[Math.floorMod(key.hashCode(),locks.length)];
        boolean acquired=false;
        try {
            acquired=lock.tryLock(20,TimeUnit.SECONDS);
            if(!acquired) throw new DatasetApiException(503,"该地点的气象查询仍在进行，请稍后重试。");
            Entry cached;
            synchronized(cache) { cached=cache.get(key); }
            boolean hit=cached!=null && clock.instant().isBefore(cached.expires());
            if(hit && single && cached.data()!=null && Instant.parse((String)cached.data().get("observed_at")).isBefore(clock.instant().minusSeconds(1800))) hit=false;
            if(!hit) {
                consume(actor.id());
                Instant fetched=clock.instant();
                try {
                    URI uri=URI.create("https://"+host+"/weather/v1/current/"+lat+"/"+lon+"?localTime=true");
                    Reply reply=transport.get(uri,apiKey);
                    if(reply.status()!=200) throw new DatasetApiException(502,reply.status()==429?"和风天气请求额度或频率受限，请稍后重试。":"和风天气暂不可用，请稍后重试或联系管理员核对服务配置。");
                    var observation=parseCurrent(reply.body(),fetched);
                    try {
                        URI solar=URI.create("https://"+host+"/solarradiation/v1/forecast/"+lat+"/"+lon+"?hours=1&interval=15&localTime=true");
                        Reply radiation=transport.get(solar,apiKey);
                        if(radiation.status()!=200) throw new DatasetApiException(502,"当前光照接口暂不可用。");
                        retainSolar(key,radiation.body(),fetched);
                    } catch(Exception e) {
                        if(e instanceof InterruptedException) Thread.currentThread().interrupt();
                        observation.put("detail","已获取实况温湿度；当前无法获取有效光照，暂不构场，请稍后刷新。");
                    }
                    attachLight(observation,key,fetched);
                    Instant cycleEnd=Instant.parse((String)observation.get("period_end"));
                    cached=new Entry(cycleEnd.isBefore(fetched.plusSeconds(ttlSeconds))?cycleEnd:fetched.plusSeconds(ttlSeconds),observation,null);
                } catch(Exception e) {
                    if(e instanceof InterruptedException) Thread.currentThread().interrupt();
                    DatasetApiException safe=e instanceof DatasetApiException d?d:new DatasetApiException(502,"气象请求失败或返回格式无效，请稍后重试。");
                    cached=new Entry(fetched.plusSeconds(failureSeconds),null,safe);
                }
                synchronized(cache) { cache.put(key,cached); }
            }
            if(cached.error()!=null) throw cached.error();
            var result=new LinkedHashMap<String,Object>(cached.data());
            if(single) {
                result.remove("period_start");result.remove("period_end");
                result.put("monitoring_mode","single_shot");result.put("field_time",clock.instant().toString());
                var weather=new LinkedHashMap<String,Object>((Map<String,Object>)result.get("weather"));weather.put("bg_light",null);result.put("weather",weather);
                for(String field:List.of("light_time","light_conversion","light_source","light_policy","light_fetched_at","light_source_tag"))result.remove(field);
                result.put("construction_ready",false);result.put("detail","已获取实况温湿度；暂无最近可用的光照预报，暂不构场。");
                SolarSample chosen=null;long distance=Long.MAX_VALUE;Instant now=clock.instant();
                synchronized(solarSeries) {
                    var series=solarSeries.get(key);
                    if(series!=null)for(var sample:series.values()) {
                        if(sample.time().isBefore(now.minusSeconds(900)) || sample.time().isAfter(now.plusSeconds(3600)))continue;
                        long delta=java.time.Duration.between(now,sample.time()).abs().toMillis();
                        if(delta<distance || delta==distance && chosen!=null && sample.time().isBefore(chosen.time())){chosen=sample;distance=delta;}
                    }
                }
                if(chosen!=null)applyLight(result,chosen);
            }
            result.put("location",location);
            result.put("requested_coordinates",Map.of("latitude",latitude,"longitude",longitude,"coordinate_system","GCJ-02"));
            result.put("query_coordinates",Map.of("latitude",Double.parseDouble(lat),"longitude",Double.parseDouble(lon),"coordinate_system","GCJ-02"));
            result.put("cached",hit);result.put("cache_expires_at",cached.expires().toString());result.put("expires_at",cached.expires().toString());
            // The construction endpoint accepts only this account-bound ticket, never weather
            // values posted by a browser. The fingerprint excludes fetch/cache bookkeeping.
            var identity=new LinkedHashMap<String,Object>();
            for(String field:List.of("provider","data_kind","monitoring_mode","field_time","period_start","period_end","observed_at","light_time","light_policy","query_coordinates","weather","light_conversion")) identity.put(field,result.get(field));
            try {
                result.put("source_fingerprint",AccountService.hash(mapper.writer().with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).writeValueAsString(identity)));
            } catch(Exception e) { throw new IllegalStateException(e); }
            String ticket=UUID.randomUUID().toString();result.put("query_id",ticket);
            synchronized(tickets) {
                tickets.values().removeIf(t->!clock.instant().isBefore(t.expires()));
                tickets.put(ticket,new Ticket(actor.id(),clock.instant().plusSeconds(120),mapper.valueToTree(result)));
            }
            return result;
        } catch(InterruptedException e) { Thread.currentThread().interrupt();throw new DatasetApiException(503,"气象查询已中断，请重试。"); }
        finally { if(acquired) lock.unlock(); }
    }
    public Map<String,Object> requireSnapshot(Account actor,String id) {
        Ticket ticket;
        synchronized(tickets) { ticket=tickets.get(id); }
        if(ticket==null || !actor.id().equals(ticket.owner()) || !clock.instant().isBefore(ticket.expires()))
            throw new DatasetApiException(409,"气象查询凭据已失效，请刷新气象后重试自动构场。");
        if(!"single_shot".equals(ticket.snapshot().path("monitoring_mode").asText()) && !clock.instant().isBefore(Instant.parse(ticket.snapshot().path("period_end").asText())))
            throw new DatasetApiException(409,"本轮 15 分钟监测周期已结束，请刷新后重试。");
        return mapper.convertValue(ticket.snapshot(),new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>() {});
    }
    private double coordinate(Map<String,Object> body,String name,double min,double max) {
        Object v=body.get(name);
        if(!(v instanceof Number n) || !Double.isFinite(n.doubleValue()) || n.doubleValue()<min || n.doubleValue()>max)
            throw new DatasetApiException(422,name+" 必须是有效经纬度数值。");
        return ((Number)v).doubleValue();
    }
    private String rounded(double value) { return BigDecimal.valueOf(value).setScale(2,RoundingMode.HALF_UP).toPlainString(); }
    private void consume(String user) {
        Instant now=clock.instant();
        synchronized(budgets) {
            var previous=budgets.get(user);
            if(previous==null || !now.isBefore(previous.since().plusSeconds(60))) budgets.put(user,new Budget(now,1));
            else {
                if(previous.count()>=requestsPerMinute) throw new DatasetApiException(429,"地点切换过于频繁，请稍后再查询新地点。");
                budgets.put(user,new Budget(previous.since(),previous.count()+1));
            }
        }
    }
    private double numeric(JsonNode node) {
        if(!node.isNumber() || !Double.isFinite(node.doubleValue())) throw new DatasetApiException(502,"气象数据缺少有效温度、湿度或辐照度。");
        return node.doubleValue();
    }
    private Instant periodStart(Instant when) { return Instant.ofEpochSecond(Math.floorDiv(when.getEpochSecond(),900)*900); }
    private Map<String,Object> parseCurrent(String body,Instant fetched) throws Exception {
        JsonNode root=mapper.readTree(body),temperature=root.path("temperature");
        Instant when=OffsetDateTime.parse(root.path("validTime").asText()).toInstant();
        if(when.isAfter(clock.instant()) || when.isBefore(fetched.minusSeconds(1800))) throw new DatasetApiException(502,"未返回当前有效的实况温湿度，暂不使用未来或过期数据。");
        if(!Set.of("°C","℃").contains(temperature.path("unit").asText())) throw new DatasetApiException(502,"实况温度单位不符合接入要求。");
        double temp=numeric(temperature.path("value")),fraction=numeric(root.path("humidity"));
        if(fraction<0 || fraction>1) throw new DatasetApiException(502,"实况湿度范围无效。");
        var result=new LinkedHashMap<String,Object>();
        result.put("provider","qweather");result.put("data_kind","current");
        result.put("observed_at",when.toString());result.put("fetched_at",fetched.toString());
        Instant start=periodStart(fetched);result.put("field_time",start.toString());
        result.put("period_start",start.toString());result.put("period_end",start.plusSeconds(900).toString());
        var weather=new LinkedHashMap<String,Object>();weather.put("bg_temp",temp);weather.put("bg_rh",fraction*100);weather.put("bg_light",null);
        result.put("weather",weather);result.put("weather_units",Map.of("bg_temp","°C","bg_rh","%","bg_light","lux"));
        result.put("light_conversion",null);result.put("light_time",null);result.put("construction_ready",false);
        result.put("detail","已获取实况温湿度；暂无本轮监测周期可用的光照近似值，暂不构场。");
        result.put("raw_weather",Map.of("temperature",Map.of("value",temp,"unit","°C"),"humidity_fraction",fraction));
        result.put("source_tag",root.path("metadata").path("tag").asText(""));
        result.put("attributions",credits(root));
        return result;
    }
    private void retainSolar(String key,String body,Instant fetched) throws Exception {
        JsonNode root=mapper.readTree(body),forecasts=root.path("forecasts");
        if(!forecasts.isArray()) throw new DatasetApiException(502,"和风天气暂未返回可用预报。");
        List<String> attribution=credits(root);String tag=root.path("metadata").path("tag").asText("");
        synchronized(solarSeries) {
        var series=solarSeries.computeIfAbsent(key,ignored->new java.util.TreeMap<>());
        series.headMap(periodStart(fetched),false).clear();
        for(JsonNode candidate:forecasts) {
            Instant valid=OffsetDateTime.parse(candidate.path("forecastTime").asText()).toInstant();
            if(valid.isBefore(periodStart(fetched)) || valid.isAfter(fetched.plusSeconds(7200))) continue;
            JsonNode ghi=candidate.path("ghi");
            if(!Set.of("W/m²","W/m2").contains(ghi.path("unit").asText()) || numeric(ghi.path("value"))<0) continue;
            series.put(valid,new SolarSample(valid,fetched,candidate.deepCopy(),tag,attribution));
        }
        while(series.size()>32) series.pollLastEntry();
        }
    }
    private void attachLight(Map<String,Object> result,String key,Instant fetched) {
        Instant start=Instant.parse((String)result.get("period_start")),end=Instant.parse((String)result.get("period_end"));
        SolarSample chosen=null;
        synchronized(solarSeries) {
            var series=solarSeries.get(key);
            if(series!=null) {
                var candidate=series.floorEntry(end);
                if(candidate!=null && !candidate.getKey().isBefore(start)) chosen=candidate.getValue();
            }
        }
        if(chosen==null) return;
        applyLight(result,chosen);
    }
    private void applyLight(Map<String,Object> result,SolarSample chosen) {
        JsonNode ghi=chosen.row().path("ghi");
        if(!Set.of("W/m²","W/m2").contains(ghi.path("unit").asText())) throw new DatasetApiException(502,"辐照度单位不符合接入要求。");
        double irradiance=numeric(ghi.path("value"));
        if(irradiance<0) throw new DatasetApiException(502,"气象辐照度范围无效。");
        WeatherLightNormalizer.Light normalized;
        try { normalized=light.normalize(irradiance,ghi.path("unit").asText()); }
        catch(DatasetApiException e) { throw new DatasetApiException(502,"气象辐照度超出可换算范围。"); }
        var mergedCredits=new java.util.LinkedHashSet<Object>((List<?>)result.get("attributions"));mergedCredits.addAll(chosen.credits());
        var weather=new LinkedHashMap<String,Object>((Map<String,Object>)result.get("weather"));weather.put("bg_light",normalized.lux());result.put("weather",weather);
        result.put("light_conversion",normalized.metadata());
        var raw=new LinkedHashMap<String,Object>((Map<String,Object>)result.get("raw_weather"));raw.put("ghi",Map.of("value",irradiance,"unit","W/m²"));result.put("raw_weather",raw);
        boolean single="single_shot".equals(result.get("monitoring_mode"));
        result.put("light_time",chosen.time().toString());result.put("light_source",single?"nearest_available_forecast":"forecast_period_proxy");
        result.put("light_policy",single?"single_shot_nearest_forecast":"period_end_proxy");result.put("light_fetched_at",chosen.fetched().toString());
        if(single)result.put("light_lead_seconds",java.time.Duration.between(Instant.parse((String)result.get("field_time")),chosen.time()).getSeconds());
        result.put("light_source_tag",chosen.tag());result.put("attributions",List.copyOf(mergedCredits));
        result.put("construction_ready",true);result.put("detail",single?"使用最新实况温湿度和最近可用辐射预报进行一次构场，结果保持至用户主动重新构场。":"以本周期末端的辐射预报近似本周期光照，温度场保持至下一轮 15 分钟更新。");
    }
    private List<String> credits(JsonNode root) {
        var attribution=new ArrayList<String>();
        JsonNode credits=root.path("metadata").path("attributions");
        if(credits.isArray()) for(JsonNode credit:credits) {
            if(!credit.isTextual() || credit.asText().length()>4096 || attribution.size()>=16) throw new DatasetApiException(502,"气象来源声明格式无效。");
            attribution.add(credit.asText());
        }
        return List.copyOf(attribution);
    }

    static class HttpTransport implements Transport {
        @Override public Reply get(URI uri,String key) throws Exception {
            var connection=(HttpURLConnection)uri.toURL().openConnection();
            connection.setConnectTimeout(5000);connection.setReadTimeout(12000);connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("X-QW-Api-Key",key);connection.setRequestProperty("Accept","application/json");connection.setRequestProperty("Accept-Encoding","gzip");
            try {
                int status=connection.getResponseCode();
                InputStream stream=status==200?connection.getInputStream():connection.getErrorStream();
                if(stream==null) return new Reply(status,"");
                try(InputStream raw=stream;InputStream body="gzip".equalsIgnoreCase(connection.getContentEncoding())?new GZIPInputStream(raw):raw) {
                    byte[] bytes=body.readNBytes(1024*1024+1);
                    if(bytes.length>1024*1024) throw new IllegalStateException("Response too large");
                    return new Reply(status,new String(bytes,StandardCharsets.UTF_8));
                }
            } finally { connection.disconnect(); }
        }
    }
}
