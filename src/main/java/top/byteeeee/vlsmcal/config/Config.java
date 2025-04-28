package top.byteeeee.vlsmcal.config;

import top.byteeeee.vlsmcal.VLSMCalculate;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Properties;

public class Config {
    private static final String CONFIG_FILE = "./config/VLSM-Calculate-Settings.properties";

    public static void saveSetting(String key, String value) {
        Properties prop = loadProperties();
        try {
            Path path = Paths.get(CONFIG_FILE);
            Files.createDirectories(path.getParent());
            try (OutputStream output = Files.newOutputStream(path)) {
                prop.setProperty(key, value);
                prop.store(output, null);
            }
        } catch (IOException io) {
            VLSMCalculate.logger.warning(io.getMessage());
        }
    }

    public static String loadSetting(String key, String defaultValue) {
        Properties prop = loadProperties();
        return prop.getProperty(key, defaultValue);
    }

    private static Properties loadProperties() {
        Properties prop = new Properties();
        Path configPath = Paths.get(CONFIG_FILE);
        if (Files.notExists(configPath)) {
            createConfigFile();
        }
        try (InputStream input = Files.newInputStream(configPath)) {
            prop.load(input);
        } catch (IOException io) {
            VLSMCalculate.logger.warning(io.getMessage());
        }
        return prop;
    }

    private static void createConfigFile() {
        try {
            Path path = Paths.get(CONFIG_FILE);
            Files.createDirectories(path.getParent());
            Files.createFile(path);
        } catch (IOException io) {
            VLSMCalculate.logger.warning(io.getMessage());
        }
    }
}
