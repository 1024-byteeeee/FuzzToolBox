package top.byteeeee.vlsmcal.settings;

import com.github.weisj.darklaf.LafManager;
import com.github.weisj.darklaf.theme.*;

import top.byteeeee.vlsmcal.VLSMCalculate;
import top.byteeeee.vlsmcal.config.Config;

import javax.swing.*;
import javax.swing.plaf.FontUIResource;
import java.awt.*;
import java.util.Enumeration;
import java.util.Objects;

public class Setting {
    public static final Font DEFAULT_FONT = new Font("Microsoft YaHei", Font.PLAIN, 24);
    private static Font currentFont = DEFAULT_FONT;
    private static String currentTheme = "One Dark";

    public static void showSettingScreen(Component parentComponent) {
        JFrame settingsFrame = new JFrame("软件设置");
        settingsFrame.setSize(700, 400);
        settingsFrame.setLayout(new GridBagLayout());
        settingsFrame.setResizable(true);
        settingsFrame.setIconImage(VLSMCalculate.aNullIcon);
        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        JLabel themeLabel = new JLabel("选择主题：");
        gbc.gridx = 0;
        gbc.gridy = 0;
        gbc.gridwidth = 1;
        settingsFrame.add(themeLabel, gbc);

        final JComboBox<String> themeComboBox = new JComboBox<>(
            new String[]{
                "Solarized Dark",
                "Solarized Light",
                "One Dark",
                "Darcula",
                "HighContrastDark",
                "HighContrastLight",
                "IntelliJ"
            }
        );
        themeComboBox.setSelectedItem(currentTheme);
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.gridwidth = 1;
        settingsFrame.add(themeComboBox, gbc);

        JLabel fontLabel = new JLabel("选择字体：");
        gbc.gridx = 0;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        settingsFrame.add(fontLabel, gbc);

        final JComboBox<String> fontComboBox = new JComboBox<>(GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames());
        fontComboBox.setSelectedItem(currentFont.getFamily());
        gbc.gridx = 1;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        settingsFrame.add(fontComboBox, gbc);

        JLabel styleLabel = new JLabel("选择字体格式：");
        gbc.gridx = 0;
        gbc.gridy = 2;
        gbc.gridwidth = 1;
        settingsFrame.add(styleLabel, gbc);

        final JComboBox<String> styleComboBox = new JComboBox<>(new String[]{"Plain", "Bold", "Italic"});
        styleComboBox.setSelectedItem(getFontStyleString(currentFont.getStyle()));
        gbc.gridx = 1;
        gbc.gridy = 2;
        gbc.gridwidth = 1;
        settingsFrame.add(styleComboBox, gbc);

        JButton applyButton = new JButton("应用");
        applyButton.addActionListener(e -> {
            String selectedFont = (String) fontComboBox.getSelectedItem();
            String selectedStyle = (String) styleComboBox.getSelectedItem();
            String selectedTheme = (String) themeComboBox.getSelectedItem();

            int fontStyle = Font.PLAIN;
            if (selectedStyle != null) {
                switch (selectedStyle) {
                    case "Bold":
                        fontStyle = Font.BOLD;
                        break;
                    case "Italic":
                        fontStyle = Font.ITALIC;
                        break;
                    default:
                        break;
                }
            }

            currentFont = new Font(selectedFont, fontStyle, currentFont.getSize());
            if (!Objects.equals(selectedTheme, currentTheme)) {
                setTheme(Objects.requireNonNull(selectedTheme));
                currentTheme = selectedTheme;
            }
            setUIFont(new FontUIResource(currentFont), parentComponent);
            SwingUtilities.updateComponentTreeUI(settingsFrame);
            saveSettings();
        });

        gbc.gridx = 0;
        gbc.gridy = 3;
        gbc.gridwidth = 2;
        settingsFrame.add(applyButton, gbc);
        settingsFrame.setLocationRelativeTo(parentComponent);
        settingsFrame.setVisible(true);
    }

    public static void setUIFont(FontUIResource f, Component component) {
        Enumeration<Object> keys = UIManager.getDefaults().keys();
        while (keys.hasMoreElements()) {
            Object key = keys.nextElement();
            Object value = UIManager.get(key);
            if (value instanceof FontUIResource) {
                UIManager.put(key, f);
            }
        }
        SwingUtilities.updateComponentTreeUI(component);
    }

    public static void setTheme(String themeName) {
        SwingUtilities.invokeLater(() -> {
            switch (themeName) {
                case "Solarized Dark" -> LafManager.install(new SolarizedDarkTheme());
                case "Solarized Light" -> LafManager.install(new SolarizedLightTheme());
                case "One Dark" -> LafManager.install(new OneDarkTheme());
                case "Darcula" -> LafManager.install(new DarculaTheme());
                case "HighContrastDark" -> LafManager.install(new HighContrastDarkTheme());
                case "HighContrastLight" -> LafManager.install(new HighContrastLightTheme());
                case "IntelliJ" -> LafManager.install(new IntelliJTheme());
            }
            for (Window window : Window.getWindows()) {
                SwingUtilities.updateComponentTreeUI(window);
            }
            LafManager.getPreferredThemeStyle();
            LafManager.updateLaf();
            saveSettings();
        });
    }

    private static String getFontStyleString(int style) {
        return switch (style) {
            case Font.BOLD -> "Bold";
            case Font.ITALIC -> "Italic";
            default -> "Plain";
        };
    }

    private static void saveSettings() {
        Config.saveSetting("currentFont", currentFont.getFontName());
        Config.saveSetting("currentFontStyle", Integer.toString(currentFont.getStyle()));
        Config.saveSetting("currentTheme", currentTheme);
    }

    @SuppressWarnings("all")
    public static void loadSettings(Component component) {
        String fontName = Config.loadSetting("currentFont", DEFAULT_FONT.getFontName());
        int fontStyle = Integer.parseInt(Config.loadSetting("currentFontStyle", Integer.toString(DEFAULT_FONT.getStyle())));
        currentFont = new Font(fontName, fontStyle, DEFAULT_FONT.getSize());
        currentTheme = Config.loadSetting("currentTheme", "One Dark");
        setTheme(currentTheme);
        setUIFont(new FontUIResource(currentFont), component);
        SwingUtilities.updateComponentTreeUI(component);
    }
}