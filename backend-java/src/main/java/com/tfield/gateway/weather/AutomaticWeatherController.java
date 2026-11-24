package com.tfield.gateway.weather;

import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.security.Account;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/** Continue a successful, authenticated weather query through the published G → F package. */
@RestController
public class AutomaticWeatherController {
    private final QWeatherClient queries;
    private final WeatherService weather;
    private final WeatherLiveService live;
    private final String defaultProfile;
    public AutomaticWeatherController(QWeatherClient queries,WeatherService weather,WeatherLiveService live,
            @Value("${tfield.weather.default-greenhouse-id:}") String defaultProfile) {
        this.queries=queries;this.weather=weather;this.live=live;this.defaultProfile=defaultProfile;
    }
    @PostMapping("/api/live/weather/construct")
    public Object construct(@AuthenticationPrincipal Account actor,@RequestBody Map<String,Object> body) {
        if(!body.keySet().equals(java.util.Set.of("query_id")) && !body.keySet().equals(java.util.Set.of("query_id","dimensions"))) throw new DatasetApiException(422,"自动构场只接受 query_id 和棚体尺寸。");
        String id=WeatherService.uuid(WeatherService.text(body,"query_id",36));
        var snapshot=queries.requireSnapshot(actor,id);
        if(!"current".equals(snapshot.get("data_kind")) || !Boolean.TRUE.equals(snapshot.get("construction_ready")))
            throw new DatasetApiException(409,String.valueOf(snapshot.getOrDefault("detail","实时构场需要实况温湿度和本周期可用的光照近似值。")));
        if(body.containsKey("dimensions"))return live.submitPrototype(actor,snapshot,body.get("dimensions"));
        if(defaultProfile.isBlank()) {
            try { weather.resolveProfile(null); }
            catch(DatasetApiException e) {
                if(e.status()==409) throw new DatasetApiException(409,"存在多份启用的棚体配置，请管理员设置服务端默认构场配置 TFIELD_AUTOMATIC_GREENHOUSE_ID。");
                throw e;
            }
        }
        return live.withStatus(weather.submitFromQuery(actor,snapshot,defaultProfile));
    }
    @GetMapping("/api/live/prototype")
    public Object prototypeInfo(){return live.prototypeInfo();}
}
