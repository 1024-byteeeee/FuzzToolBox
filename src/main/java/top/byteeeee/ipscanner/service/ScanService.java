package top.byteeeee.ipscanner.service;

public interface ScanService {
    void startScan(String startIP, String endIP, int threadCount, int timeout);
    void requestStopScan();
    void stopScan();
}
