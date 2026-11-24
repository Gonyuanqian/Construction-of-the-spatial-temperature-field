package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import com.tfield.gateway.dataset.DatasetApiException;
import org.junit.jupiter.api.Test;

class WeatherLightNormalizerTest {
    final WeatherLightNormalizer normalizer=new WeatherLightNormalizer(110);

    @Test void luxIsNotMultipliedEvenWhenItsValueIsSmall() {
        for(String unit:new String[]{"lux","lx"," LUX "}) {
            var light=normalizer.normalize(.5,unit);
            assertEquals(.5,light.lux()); assertFalse(light.converted());
            assertEquals("identity",light.metadata().get("method"));
            assertEquals(false,light.metadata().get("estimated"));
        }
    }
    @Test void horizontalIrradianceHasExplicitEstimatedProvenance() {
        for(String unit:new String[]{"W/m²","W/m2"}) {
            var light=normalizer.normalize(500,unit);
            assertEquals(55000,light.lux());
            assertEquals("W/m²",light.metadata().get("source_unit"));
            assertEquals(500.,light.metadata().get("source_value"));
            assertEquals("lux",light.metadata().get("target_unit"));
            assertEquals(55000.,light.metadata().get("target_value"));
            assertEquals(110.,light.metadata().get("efficacy_lm_per_w"));
            assertEquals("daylight_constant_v1",light.metadata().get("method"));
            assertEquals(false,light.metadata().get("calibrated"));
        }
    }
    @Test void nightZeroRemainsZero() {
        assertEquals(0.,normalizer.normalize(0,"W/m²").lux());
    }
    @Test void coefficientIsControlledByTheServer() {
        assertEquals(60000.,new WeatherLightNormalizer(120).normalize(500,"W/m²").lux());
    }
    @Test void invalidConfigurationCannotStartSilently() {
        for(double coefficient:new double[]{0,-1,Double.NaN,Double.POSITIVE_INFINITY})
            assertThrows(IllegalArgumentException.class,()->new WeatherLightNormalizer(coefficient));
    }
    @Test void invalidMeasurementsAreRejected() {
        for(double value:new double[]{-1,Double.NaN,Double.NEGATIVE_INFINITY,Double.POSITIVE_INFINITY,Double.MAX_VALUE})
            assertEquals(422,assertThrows(DatasetApiException.class,()->normalizer.normalize(value,"W/m²")).status());
    }
    @Test void unitsAreNeverGuessedFromMagnitude() {
        for(Object unit:new Object[]{null,12,"","klux","W","watts"})
            assertEquals(422,assertThrows(DatasetApiException.class,()->normalizer.normalize(500,unit)).status());
    }
}
