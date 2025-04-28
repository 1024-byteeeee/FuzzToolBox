package top.byteeeee.ipscanner.util;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MacAddrUtil {
    private static String macAddr = "未知";
    private static Process process;
    private static BufferedReader bufReader;

    public static String getAddr(String ip) {
        try {
            ProcessBuilder pb = new ProcessBuilder(getCompatSystemCommand(ip));
            pb.redirectErrorStream(true);
            process = pb.start();
            bufReader = new BufferedReader(new InputStreamReader(process.getInputStream()), 8192);
            macAddrFormat();
            process.waitFor(1, TimeUnit.SECONDS);
            return macAddr;
        } catch (IOException | InterruptedException e) {
            return macAddr;
        } finally {
            try {
                if (bufReader != null) {
                    bufReader.close();
                }
                if (process != null) {
                    process.destroyForcibly();
                }
            } catch (IOException ignored) {}
        }
    }

    private static String[] getCompatSystemCommand(String ip) {
        String osName = System.getProperty("os.name").toLowerCase();
        if (osName.contains("win")) {
            return new String[]{"arp", "-a", ip};
        } else if (osName.contains("mac") || osName.contains("darwin")) {
            return new String[]{"arp", "-n", ip};
        } else {
            return new String[]{"arp", "-n", ip};
        }
    }

    private static void macAddrFormat() throws IOException {
        String line;
        Pattern macPattern = Pattern.compile("([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}");
        while ((line = bufReader.readLine()) != null) {
            Matcher matcher = macPattern.matcher(line);
            if (matcher.find()) {
                macAddr = matcher.group().replace(":", "-").toUpperCase();
                break;
            }
        }
    }
}
