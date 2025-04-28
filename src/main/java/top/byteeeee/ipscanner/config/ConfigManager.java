package top.byteeeee.ipscanner.config;

import java.io.*;
import java.util.Properties;

public class ConfigManager {
    private static final String CONFIG_FILE = "./config/IP-Scanner-Settings.properties";
    private static final Properties properties = new Properties();

    public static void loadConfig() {
        File configFile = new File(CONFIG_FILE);
        File parentDir = configFile.getParentFile();

        if (parentDir != null && !parentDir.exists()) {
            boolean dirsCreated = parentDir.mkdirs();
            if (!dirsCreated) {
                System.err.println("无法创建配置目录: " + parentDir.getAbsolutePath());
            }
        }

        if (configFile.exists()) {
            try (FileInputStream fis = new FileInputStream(configFile)) {
                properties.load(fis);
            } catch (IOException e) {
                System.err.println("加载配置文件出错: " + e.getMessage());
            }
        }
    }

    public static void saveConfig() {
        File configFile = new File(CONFIG_FILE);
        try (FileOutputStream fos = new FileOutputStream(configFile)) {
            properties.store(fos, "IPScanner 配置文件");
        } catch (IOException e) {
            System.err.println("保存配置文件出错: " + e.getMessage());
        }
    }

    public static String getProperty(String key, String defaultValue) {
        return properties.getProperty(key, defaultValue);
    }

    public static void setProperty(String key, String value) {
        properties.setProperty(key, value);
        saveConfig();
    }

    static {
        loadConfig();
    }
}