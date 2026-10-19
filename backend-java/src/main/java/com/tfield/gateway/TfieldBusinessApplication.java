package com.tfield.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TfieldBusinessApplication {
    public static void main(String[] args) {
        SpringApplication.run(TfieldBusinessApplication.class, args);
    }
}
