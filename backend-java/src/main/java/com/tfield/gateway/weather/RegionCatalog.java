package com.tfield.gateway.weather;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/** One authoritative dictionary for both forms and server-side location validation. */
@Component
public class RegionCatalog {
    private final JsonNode catalog;
    public RegionCatalog(ObjectMapper mapper) {
        try (var stream=new ClassPathResource("regions/jilin.json").getInputStream()) {
            catalog=mapper.readTree(stream);
        } catch(IOException e) { throw new IllegalStateException("吉林省地区字典读取失败",e); }
    }
    public JsonNode data() { return catalog.deepCopy(); }
    public Map<String,Object> validate(Object raw) {
        if(!(raw instanceof Map<?,?> input) || !Set.of("province_code","city_code","district_code").containsAll(input.keySet()))
            throw new DatasetApiException(422,"location 必须包含省、市、可选区县的行政区划代码。");
        if(!"220000".equals(input.get("province_code"))) throw new DatasetApiException(422,"当前地区库仅支持吉林省。");
        for(var city:catalog.path("cities")) if(city.path("code").asText().equals(input.get("city_code"))) {
            var result=new LinkedHashMap<String,Object>();
            result.put("province_code","220000"); result.put("province_name","吉林省");
            result.put("city_code",city.path("code").asText()); result.put("city_name",city.path("name").asText());
            Object code=input.get("district_code");
            if(code==null || "".equals(code)) return result;
            for(var district:city.path("districts")) if(district.path("code").asText().equals(code)) {
                result.put("district_code",code); result.put("district_name",district.path("name").asText()); return result;
            }
            throw new DatasetApiException(422,"区县代码不属于所选市（州）。");
        }
        throw new DatasetApiException(422,"请选择有效的吉林省市（州）。");
    }
}
