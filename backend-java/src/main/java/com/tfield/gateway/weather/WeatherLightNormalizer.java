package com.tfield.gateway.weather;

import com.tfield.gateway.dataset.DatasetApiException;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Normalize external light once, before both G and F receive the training-scale lux. */
@Component
public class WeatherLightNormalizer {
    public static final String LUX="lux";
    public static final String IRRADIANCE="W/m²";
    private final double daylightEfficacy;

    public WeatherLightNormalizer(@Value("${tfield.weather.light-efficacy-lm-per-w:110}") double daylightEfficacy) {
        if(!Double.isFinite(daylightEfficacy) || daylightEfficacy<=0)
            throw new IllegalArgumentException("日光光效系数必须是大于 0 的有限数值。");
        this.daylightEfficacy=daylightEfficacy;
    }

    public Light normalize(double sourceValue,Object rawUnit) {
        if(!Double.isFinite(sourceValue) || sourceValue<0)
            throw new DatasetApiException(422,"背景光照必须是非负有限数值。");
        if(!(rawUnit instanceof String text))
            throw new DatasetApiException(422,"bg_light_unit 必须为 lux 或 W/m²。");
        String unit=switch(text.trim().toLowerCase(Locale.ROOT)) {
            case "lux","lx" -> LUX;
            case "w/m²","w/m2" -> IRRADIANCE;
            default -> throw new DatasetApiException(422,"bg_light_unit 仅支持 lux、lx、W/m² 或 W/m2，不按数值大小猜测单位。");
        };
        double factor=IRRADIANCE.equals(unit)?daylightEfficacy:1.;
        double lux=sourceValue*factor;
        if(!Double.isFinite(lux)) throw new DatasetApiException(422,"换算后的背景光照超出有限数值范围。");
        return new Light(sourceValue,unit,lux,factor);
    }

    public record Light(double sourceValue,String sourceUnit,double lux,double factor) {
        public boolean converted() { return IRRADIANCE.equals(sourceUnit); }
        public Map<String,Object> metadata() {
            var result=new LinkedHashMap<String,Object>();
            result.put("source_value",sourceValue); result.put("source_unit",sourceUnit);
            result.put("target_value",lux); result.put("target_unit",LUX);
            result.put("method",converted()?"daylight_constant_v1":"identity");
            result.put("factor",factor); result.put("estimated",converted());
            if(converted()) {
                result.put("efficacy_lm_per_w",factor);
                result.put("assumption","outdoor_horizontal_daylight");
                result.put("calibrated",false);
            }
            return result;
        }
    }
}
