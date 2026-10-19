package com.tfield.gateway.api;

import com.tfield.gateway.dataset.DatasetApiException;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.transaction.TransactionException;
import com.tfield.gateway.training.TrainingConflict;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;

@RestControllerAdvice
public class DatasetErrorAdvice {
    private static final Logger LOG = LoggerFactory.getLogger(DatasetErrorAdvice.class);

    @ExceptionHandler(TrainingConflict.class)
    public ResponseEntity<?> trainingConflict(TrainingConflict exception) {
        return ResponseEntity.status(409).body(Map.of("detail", exception.getMessage(), "job_id", exception.jobId()));
    }

    @ExceptionHandler(DatasetApiException.class)
    public ResponseEntity<?> dataset(DatasetApiException exception) {
        return ResponseEntity.status(exception.status()).body(Map.of("detail", exception.getMessage()));
    }

    @ExceptionHandler({DataAccessException.class, TransactionException.class})
    public ResponseEntity<?> database(RuntimeException exception) {
        LOG.error("Business persistence failed type={}", exception.getClass().getSimpleName());
        return ResponseEntity.status(503).body(Map.of("detail", "业务记录暂不可用，请稍后刷新确认操作结果。"));
    }

    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<?> connection(ResourceAccessException exception) {
        return ResponseEntity.status(503).body(Map.of("detail", "计算服务暂不可用，请稍后查询任务或工作区状态。"));
    }

    @ExceptionHandler(RestClientException.class)
    public ResponseEntity<?> upstream(RestClientException exception) {
        return ResponseEntity.status(502).body(Map.of("detail", "计算服务返回异常，请稍后查询任务或工作区状态。"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<?> invalidJson(HttpMessageNotReadableException exception) {
        return ResponseEntity.status(400).body(Map.of("detail", "请求内容不是有效的 JSON。"));
    }
}
