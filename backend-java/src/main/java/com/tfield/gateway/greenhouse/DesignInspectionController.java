package com.tfield.gateway.greenhouse;
import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.security.Account;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user/greenhouse-designs")
public class DesignInspectionController {
    private final DesignInspectionService service;
    public DesignInspectionController(DesignInspectionService service){this.service=service;}
    @GetMapping("/inspection-capabilities") public Object capabilities(@AuthenticationPrincipal Account a){return service.capabilities(a);}
    @PostMapping("/{id}/inspections") public Object submit(@AuthenticationPrincipal Account a,@PathVariable UUID id,@RequestBody JsonNode body){
        DesignLayout.require(body.size()==2&&body.has("revision")&&body.has("request_key")&&body.path("revision").isIntegralNumber()&&body.path("revision").asLong()>0&&body.path("request_key").isTextual(),"检验仅接受已保存版本号及请求编号。");
        String key;try{key=UUID.fromString(body.path("request_key").asText()).toString();}catch(Exception e){throw new com.tfield.gateway.dataset.DatasetApiException(422,"检验请求编号无效。");}
        return service.submit(a,id.toString(),body.path("revision").asLong(),key);
    }
    @GetMapping("/{id}/inspections/latest") public Object latest(@AuthenticationPrincipal Account a,@PathVariable UUID id){return service.latest(a,id.toString());}
    @GetMapping("/{id}/inspections") public Object history(@AuthenticationPrincipal Account a,@PathVariable UUID id){return service.history(a,id.toString());}
    @GetMapping("/{id}/inspections/{inspectionId}") public Object get(@AuthenticationPrincipal Account a,@PathVariable UUID id,@PathVariable UUID inspectionId){return service.get(a,id.toString(),inspectionId.toString());}
    @PostMapping("/{id}/inspections/{inspectionId}/cancel") public Object cancel(@AuthenticationPrincipal Account a,@PathVariable UUID id,@PathVariable UUID inspectionId){return service.cancel(a,id.toString(),inspectionId.toString());}
}
