package top.byteeeee.ipscanner.impl;

import javafx.animation.PauseTransition;
import javafx.application.Platform;
import javafx.scene.control.Alert;
import javafx.util.Duration;

import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.helper.AlertHelper;
import top.byteeeee.ipscanner.model.PingResult;
import top.byteeeee.ipscanner.model.ScanResult;
import top.byteeeee.ipscanner.service.ScanService;
import top.byteeeee.ipscanner.util.HostNameUtil;
import top.byteeeee.ipscanner.util.IPUtils;
import top.byteeeee.ipscanner.util.MacAddrUtil;

import java.io.IOException;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.text.NumberFormat;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ScanImpl implements ScanService {
    private final MainController controller;
    private volatile boolean isStopped = false;
    private int totalIPs;
    private final AtomicInteger completedIPs = new AtomicInteger(0);
    private ExecutorService executor;
    private Semaphore taskSemaphore;
    int queueCapacity;

    private static final int MAX_QUEUE_CAPACITY = 10_0000;
    private static final Double STOP_SCAN_DELAY_S = 2.5D;
    private static final Double SCAN_DONE_DELAY_S = 2.5D;

    public ScanImpl(MainController controller) {
        this.controller = controller;
    }

    @Override
    public void startScan(String startIP, String endIP, int threadCount, int timeout) {
        try {
            completedIPs.set(0);
            controller.getData().clear();
            Iterable<String> ipIterable = IPUtils.generateIPRange(startIP, endIP);
            totalIPs = calculateTotalIPs(startIP, endIP);
            queueCapacity = calculateDynamicQueueCapacity(totalIPs, threadCount);
            int permits = threadCount + queueCapacity;
            taskSemaphore = new Semaphore(permits);
            executor = new ThreadPoolExecutor(
                threadCount, threadCount,
                2L, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(queueCapacity),
                new ThreadPoolExecutor.CallerRunsPolicy());
            controller.getStopButton().setDisable(false);
            isStopped = false;
            new Thread(() -> {
                try {
                    for (String ip : ipIterable) {
                        if (isStopped) break;
                        taskSemaphore.acquire();
                        if (isStopped) {
                            taskSemaphore.release();
                            break;
                        }
                        final String currentIp = ip;
                        executor.execute(() -> {
                            try {
                                if (isStopped) return;
                                PingResult result = pingWithTime(currentIp, timeout);
                                if (isStopped) return;
                                String hostname = HostNameUtil.getHostname(currentIp);
                                int completed = completedIPs.incrementAndGet();
                                Platform.runLater(() -> {
                                    if (isStopped) return;
                                    String status = result.isReachable() ? "在线" : "离线";
                                    String responseTime = result.isReachable() ? result.getResponseTime() : "N/A";
                                    String macAddr = result.isReachable() ? MacAddrUtil.getAddr(currentIp) : "N/A";
                                    String index = String.valueOf(controller.getData().size() + 1);
                                    controller.getData().add(new ScanResult(index, currentIp, status, responseTime, macAddr, hostname));
                                    this.updateProgress(controller, completed, totalIPs);
                                });
                            } finally {
                                taskSemaphore.release();
                            }
                        });
                    }
                } catch (RuntimeException | InterruptedException e) {
                    if (!isStopped) {
                        Platform.runLater(() -> {
                            AlertHelper.showAlert("扫描错误", "扫描过程中发生错误: " + e.getMessage(), Alert.AlertType.ERROR);
                            controller.getStartButton().setDisable(false);
                        });
                    }
                } finally {
                    if (executor != null && !executor.isShutdown()) {
                        executor.shutdown();
                    }
                }
            }).start();
        } catch (RuntimeException | UnknownHostException e) {
            AlertHelper.showAlert("扫描错误", "扫描初始化错误: " + e.getMessage(), Alert.AlertType.ERROR);
            controller.getStartButton().setDisable(false);
        }
    }

    @Override
    public void requestStopScan() {
        AlertHelper.showConfirmAlert("停止扫描", "您确认停止当前扫描吗?\n点击确认将停止扫描且无法恢复", this::stopScan);
    }

    @Override
    public void stopScan() {
        isStopped = true;
        if (executor != null) {
            executor.shutdownNow();
        }
        Platform.runLater(() -> {
            controller.getProgressBar().setProgress(0);
            controller.getStatusLabel().setText("正在停止...");
            controller.getStopButton().setDisable(true);
            PauseTransition delay = new PauseTransition(Duration.seconds(STOP_SCAN_DELAY_S));
            delay.setOnFinished(event -> {
                controller.getStatusLabel().setText("就绪");
                controller.getExportButton().setDisable(false);
                controller.getStartButton().setDisable(false);
            });
            delay.play();
        });
    }

    private int calculateTotalIPs(String startIP, String endIP) throws UnknownHostException {
        long start = IPUtils.ipToLong(InetAddress.getByName(startIP));
        long end = IPUtils.ipToLong(InetAddress.getByName(endIP));
        long total = end - start + 1;

        if (total > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("IP范围过大");
        }

        return (int) total;
    }

    private PingResult pingWithTime(String ip, int timeout) {
        try {
            long start = System.nanoTime();
            boolean reachable = InetAddress.getByName(ip).isReachable(timeout);
            long duration = (System.nanoTime() - start) / 100_0000;
            return new PingResult(reachable, duration + "ms");
        } catch (IOException e) {
            return new PingResult(false, "错误");
        }
    }

    public void updateProgress(MainController controller, int done, int totalIPs) {
        double progress = Math.min((double) done / totalIPs, 1.0D);
        NumberFormat percentFormat = NumberFormat.getPercentInstance();
        percentFormat.setMinimumFractionDigits(1);
        controller.getProgressBar().setProgress(progress);
        Platform.runLater(() -> {
            String percentage = percentFormat.format(progress);
            if (progress >= 1.0D) {
                controller.getStatusLabel().setText("扫描完成 " + percentage);
                PauseTransition delay = new PauseTransition(Duration.seconds(SCAN_DONE_DELAY_S));
                delay.onFinishedProperty().set(event -> {
                    controller.getProgressBar().setProgress(0);
                    controller.getStatusLabel().setText("就绪");
                    controller.getExportButton().setDisable(false);
                    controller.getStopButton().setDisable(true);
                    controller.getStartButton().setDisable(false);
                });
                delay.play();
            } else {
                controller.getStatusLabel().setText(String.format("扫描进度：%d / %d IP | %s", done, totalIPs, percentage));
            }
        });
    }

    private int calculateDynamicQueueCapacity(int totalIPs, int threadCount) {
        final int MIN_CAPACITY = 2000;
        final int MEDIUM_THRESHOLD = 10000;
        final int LARGE_THRESHOLD = 10_0000;
        int capacity;

        if (totalIPs <= MEDIUM_THRESHOLD) {
            capacity = 10000;
        } else if (totalIPs <= LARGE_THRESHOLD) {
            capacity = (int)(totalIPs * 0.2);
        } else {
            capacity = 50000 + (threadCount * 1000);
        }

        return Math.min(MAX_QUEUE_CAPACITY, Math.max(MIN_CAPACITY, capacity));
    }
}