package com.tfield.gateway.live;

import java.util.concurrent.locks.ReentrantLock;
import org.springframework.stereotype.Component;

/** 实时操作与确认串行化；不占用训练和模型管理的工作区协调锁。 */
@Component
public class LiveCoordinator {
    private final ReentrantLock lock = new ReentrantLock();
    public Lease acquire() { lock.lock(); return new Lease(lock); }
    public Lease tryAcquire() { return lock.tryLock() ? new Lease(lock) : null; }
    public static final class Lease implements AutoCloseable {
        private final ReentrantLock lock;
        private Lease(ReentrantLock lock) { this.lock = lock; }
        @Override public void close() { lock.unlock(); }
    }
}
