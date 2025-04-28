package top.byteeeee.ipscanner.ui.theme;

import javafx.scene.Scene;

import top.byteeeee.ipscanner.config.ConfigManager;
import top.byteeeee.ipscanner.helper.AlertHelper;

import java.util.Objects;

public class ThemeManager {
    public static final String THEME_KEY = "app.theme";
    public static final String DEFAULT_THEME = "one-dark-theme";
    public static String currentTheme = null;

    public static void init() {
        currentTheme = ConfigManager.getProperty(THEME_KEY, DEFAULT_THEME);
    }

    public static void applyTheme(Scene scene, String themeName) {
        if (scene == null) return;
        String cssPath = "/themes/" + themeName + ".css";
        try {
            scene.getStylesheets().clear();
            scene.getStylesheets().add(Objects.requireNonNull(ThemeManager.class.getResource(cssPath)).toExternalForm());
            setCurrentTheme(themeName);
        } catch (NullPointerException e) {
            AlertHelper.showThemeError(cssPath);
        }
    }

    public static String getCurrentTheme() {
        if (currentTheme == null) {
            init();
        }
        return currentTheme;
    }

    private static void setCurrentTheme(String themeName) {
        currentTheme = themeName;
        ConfigManager.setProperty(THEME_KEY, themeName);
    }
}
