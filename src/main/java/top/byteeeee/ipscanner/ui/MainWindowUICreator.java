package top.byteeeee.ipscanner.ui;

import javafx.application.Platform;
import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.scene.control.Alert;
import javafx.scene.image.Image;
import javafx.stage.Stage;

import top.byteeeee.ipscanner.IPScanner;
import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.helper.AlertHelper;
import top.byteeeee.ipscanner.ui.theme.ThemeManager;

import java.io.IOException;
import java.net.URL;

public class MainWindowUICreator implements UIBuilder {
    public static final String ICON_PATH = String.valueOf(IPScanner.class.getResource("/icon/IPScannerIcon.png"));
    private static final URL FXML_PATH = IPScanner.class.getResource("/fxml/MainView.fxml");
    private final MainController controller;

    public MainWindowUICreator(MainController controller) {
        this.controller = controller;
    }

    @Override
    public void setupUI(Stage stage) {
        try {
            FXMLLoader loader = createFxmlLoader();
            Scene scene = buildScene(loader);
            configureStage(stage, scene);
            setupCloseHandler(stage);
        } catch (IOException e) {
            handleLoadError(e);
        }
    }

    private FXMLLoader createFxmlLoader() {
        FXMLLoader loader = new FXMLLoader(FXML_PATH);
        loader.setController(controller);
        return loader;
    }

    private Scene buildScene(FXMLLoader loader) throws IOException {
        Scene scene = new Scene(loader.load(), 1222, 600);
        ThemeManager.applyTheme(scene, ThemeManager.currentTheme);
        return scene;
    }

    private void configureStage(Stage stage, Scene scene) {
        stage.getIcons().add(new Image(ICON_PATH));
        stage.setTitle("IP-Scanner " + IPScanner.APP_VERSION + " by 1024_byteeeee");
        stage.setScene(scene);
        stage.show();
    }

    private void setupCloseHandler(Stage stage) {
        stage.setOnCloseRequest(event -> {
            if (controller.isScanning()) {
                event.consume();
                showExitConfirmation();
            } else {
                shutdownApplication();
            }
        });
    }

    private void showExitConfirmation() {
        AlertHelper.showConfirmAlert("确认退出", "扫描正在进行中，确定要退出吗？\n点击确认将停止扫描并退出应用", this::shutdownApplication);
    }

    private void shutdownApplication() {
        Platform.exit();
        System.exit(0);
    }

    private void handleLoadError(IOException e) {
        AlertHelper.showAlert("错误", "无法加载界面: " + e.getMessage(), Alert.AlertType.ERROR);
        Platform.exit();
    }
}