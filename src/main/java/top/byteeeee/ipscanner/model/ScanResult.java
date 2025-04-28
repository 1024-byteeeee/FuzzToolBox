package top.byteeeee.ipscanner.model;

import javafx.beans.property.SimpleStringProperty;
import javafx.beans.property.StringProperty;

public class ScanResult {
    private final StringProperty index = new SimpleStringProperty();
    private final StringProperty ip = new SimpleStringProperty();
    private final StringProperty hostname = new SimpleStringProperty();
    private final StringProperty status = new SimpleStringProperty();
    private final StringProperty responseTime = new SimpleStringProperty();
    private final StringProperty macAddr = new SimpleStringProperty();

    public ScanResult(String index, String ip, String status, String responseTime, String macAddr, String hostname) {
        this.index.set(index);
        this.ip.set(ip);
        this.hostname.set(hostname);
        this.macAddr.set(macAddr);
        this.status.set(status);
        this.responseTime.set(responseTime);
    }

    public String getIndex() {
        return index.get();
    }

    public String getIp() {
        return ip.get();
    }

    public String getHostname() {
        return hostname.get();
    }

    public String getStatus() {
        return status.get();
    }

    public String getResponseTime() {
        return responseTime.get();
    }

    public String getMacAddr() {
        return macAddr.get();
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (obj == null || getClass() != obj.getClass()) {
            return false;
        }
        ScanResult that = (ScanResult) obj;
        return ip.get().equals(that.ip.get());
    }

    @Override
    public int hashCode() {
        return ip.get().hashCode();
    }
}
