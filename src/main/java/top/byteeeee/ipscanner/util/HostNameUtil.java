package top.byteeeee.ipscanner.util;

import java.net.InetAddress;

public class HostNameUtil {
    public static String getHostname(String ip) {
        try {
            InetAddress addr = InetAddress.getByName(ip);
            String hostname = addr.getHostName();
            return hostname.equals(ip) ? "未知" : hostname;
        } catch (Exception e) {
            return "未知";
        }
    }
}
