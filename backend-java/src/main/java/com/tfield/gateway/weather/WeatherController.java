package com.tfield.gateway.weather;

import com.tfield.gateway.security.Account;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
public class WeatherController {
    private final WeatherService service;
    public WeatherController(WeatherService service) { this.service=service; }
    @GetMapping("/api/admin/weather-models") Object models() { return service.deployments(); }
    @PostMapping("/api/admin/weather-models") Object register(@AuthenticationPrincipal Account a,@RequestBody Map<String,Object> body) { return service.register(a,body); }
    @GetMapping("/api/admin/weather-models/{id}") Object model(@PathVariable String id) { return service.deployment(id); }
    @PatchMapping("/api/admin/weather-models/{id}") Object status(@PathVariable String id,@RequestBody Map<String,Object> body) { return service.status(id,WeatherService.text(body,"status",16)); }
    @GetMapping({"/api/admin/greenhouses","/api/user/greenhouses"}) Object houses(@AuthenticationPrincipal Account a) { return service.houses(a); }
    @GetMapping({"/api/admin/greenhouses/{id}","/api/user/greenhouses/{id}"}) Object house(@AuthenticationPrincipal Account a,@PathVariable String id) { return service.house(a,id); }
    @PostMapping("/api/admin/greenhouses") Object create(@AuthenticationPrincipal Account a,@RequestBody Map<String,Object> body) { return service.createHouse(a,body); }
    @PatchMapping("/api/admin/greenhouses/{id}") Object update(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestBody Map<String,Object> body) { return service.updateHouse(a,id,body); }
    @PutMapping("/api/admin/greenhouses/{id}/weather-model") Object bind(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestBody Map<String,Object> body) { return service.bind(a,id,WeatherService.text(body,"weather_model_id",36)); }
    @GetMapping({"/api/user/regions","/api/live/regions"}) Object regions() { return service.regions(); }
    @PostMapping({"/api/user/weather/match","/api/live/match"}) Object match(@RequestBody Map<String,Object> body) { return service.resolveProfile(body.get("greenhouse_id")); }
    @PostMapping("/api/user/weather") Object weather(@AuthenticationPrincipal Account a,@RequestBody Map<String,Object> body) { return service.submit(a,body); }
    @GetMapping("/api/user/greenhouses/{id}/frames") Object frames(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestParam(defaultValue="20") int limit,@RequestParam(defaultValue="0") int offset,@RequestParam(required=false,name="region_code") String regionCode) { return service.frames(a,id,limit,offset,regionCode); }
    @GetMapping("/api/user/greenhouses/{id}/frames/{frameId}/field") Object field(@AuthenticationPrincipal Account a,@PathVariable String id,@PathVariable String frameId) { return service.field(a,id,frameId); }
}
