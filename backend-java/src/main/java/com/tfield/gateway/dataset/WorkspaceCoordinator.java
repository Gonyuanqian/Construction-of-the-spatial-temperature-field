package com.tfield.gateway.dataset;

import java.util.concurrent.locks.ReentrantLock;
import org.springframework.stereotype.Component;

/** 当前仅一个工作区：序列化数据选择与训练提交，普通计算保留自己的请求快照。 */
@Component
public class WorkspaceCoordinator {
    private final ReentrantLock lock = new ReentrantLock();

    public Lease acquire() {
        lock.lock();
        return new Lease(lock);
    }

    public static final class Lease implements AutoCloseable {
        private final ReentrantLock lock;
        private Lease(ReentrantLock lock) {
            this.lock = lock;
        }
        @Override
        public void close() {
            lock.unlock();
        }
    }
}
