package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.Map;
import org.junit.jupiter.api.Test;

class RegionCatalogTest {
    final RegionCatalog regions=new RegionCatalog(new ObjectMapper());
    @Test void officialDictionaryHasNineCitiesAndSixtyDistricts() {
        assertEquals(9,regions.data().path("cities").size());
        int count=0;
        for(var city:regions.data().path("cities")) count+=city.path("districts").size();
        assertEquals(60,count);
    }
    @Test void normalizesCityAndDistrictNamesFromCodes() {
        var normalized=regions.validate(Map.of("province_code","220000","city_code","220600","district_code","220621"));
        assertEquals("白山市",normalized.get("city_name")); assertEquals("抚松县",normalized.get("district_name"));
        assertFalse(regions.validate(Map.of("province_code","220000","city_code","220600","district_code","")).containsKey("district_code"));
    }
    @Test void rejectsForeignCrossCityAndClientSuppliedNames() {
        for(var input: java.util.List.of(
            Map.of("province_code","230000","city_code","220600"),
            Map.of("province_code","220000","city_code","220600","district_code","220202"),
            Map.of("province_code","220000","city_code","unknown"),
            Map.of("province_code","220000","city_code","220600","city_name","伪造地名")))
            assertThrows(DatasetApiException.class,()->regions.validate(input));
        assertThrows(DatasetApiException.class,()->regions.validate("吉林"));
    }
}
