package com.tfield.gateway.training;

public class TrainingConflict extends RuntimeException {
    private final String jobId;
    public TrainingConflict(String jobId) {
        super("已经有一次标定在跑"); this.jobId = jobId;
    }
    public String jobId() { return jobId; }
}
