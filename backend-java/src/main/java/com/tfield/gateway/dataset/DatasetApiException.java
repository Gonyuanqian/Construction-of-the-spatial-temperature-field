package com.tfield.gateway.dataset;

public class DatasetApiException extends RuntimeException {
    private final int status;

    public DatasetApiException(int status, String detail) {
        super(detail);
        this.status = status;
    }

    public int status() {
        return status;
    }
}
