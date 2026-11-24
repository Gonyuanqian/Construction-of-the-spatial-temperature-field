package com.tfield.gateway.greenhouse.control;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ControlScheduler {
    private final ControlService controls;private final ControlPlans plans;
    public ControlScheduler(ControlService controls,ControlPlans plans){this.controls=controls;this.plans=plans;}
    @Scheduled(fixedDelayString="${tfield.control.tick-ms:1000}") public void devices(){controls.tick();}
    @Scheduled(fixedDelayString="${tfield.control.plan-poll-ms:3000}") public void proposals(){plans.generatePending();}
}
