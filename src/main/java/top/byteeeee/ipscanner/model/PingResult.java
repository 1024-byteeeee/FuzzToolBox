package top.byteeeee.ipscanner.model;

@SuppressWarnings("ClassCanBeRecord")
public class PingResult {
    private final boolean reachable;
    private final String responseTime;

    public PingResult(boolean reachable, String responseTime) {
        this.reachable = reachable;
        this.responseTime = responseTime;
    }

    public boolean isReachable() {
        return reachable;
    }

    public String getResponseTime() {
        return responseTime;
    }
}
