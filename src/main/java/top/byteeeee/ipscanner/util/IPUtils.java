package top.byteeeee.ipscanner.util;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Iterator;

public class IPUtils {
    public static Iterable<String> generateIPRange(String startIP, String endIP) throws UnknownHostException {
        long start = ipToLong(InetAddress.getByName(startIP));
        long end = ipToLong(InetAddress.getByName(endIP));
        return () -> new Iterator<>() {
            private long current = start;

            @Override
            public boolean hasNext() {
                return current <= end;
            }

            @Override
            public String next() {
                return longToIp(current++);
            }
        };
    }

    public static long ipToLong(InetAddress ip) {
        byte[] octets = ip.getAddress();
        long result = 0;
        for (byte octet : octets) {
            result <<= 8;
            result |= octet & 0xff;
        }
        return result;
    }

    public static String longToIp(long ip) {
        return String.format("%d.%d.%d.%d", (ip >> 24) & 0xff, (ip >> 16) & 0xff, (ip >> 8) & 0xff, ip & 0xff);
    }

    @SuppressWarnings("BooleanMethodIsAlwaysInverted")
    public static boolean isValidIPv4(String ip) {
        String pattern = "^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$";
        return ip.matches(pattern);
    }
}