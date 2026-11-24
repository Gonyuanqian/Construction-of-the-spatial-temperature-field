package com.tfield.gateway.weather;

import com.tfield.gateway.security.Account;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QWeatherController {
    private final QWeatherClient client;
    public QWeatherController(QWeatherClient client) { this.client=client; }
    @PostMapping("/api/live/weather/query")
    public Object query(@AuthenticationPrincipal Account actor,@RequestBody Map<String,Object> body) {
        return client.querySingle(actor,body);
    }
}
