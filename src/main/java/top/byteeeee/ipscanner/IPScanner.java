package top.byteeeee.ipscanner;

import javafx.application.Application;
import javafx.stage.Stage;

import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.ui.MainWindowUICreator;
import top.byteeeee.ipscanner.ui.UIBuilder;
import top.byteeeee.ipscanner.ui.theme.ThemeManager;

public class IPScanner extends Application {
    public static String APP_VERSION = "v1.3.0";

    @Override
    public void start(Stage primaryStage) {
        ThemeManager.init();
        MainController controller = new MainController();
        UIBuilder uiBuilder = new MainWindowUICreator(controller);
        uiBuilder.setupUI(primaryStage);
    }

    public static void main(String[] args) {
        launch(args);
    }
}