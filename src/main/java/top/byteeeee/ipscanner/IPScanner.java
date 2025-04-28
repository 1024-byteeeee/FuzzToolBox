package top.byteeeee.ipscanner;

import javafx.application.Application;
import javafx.stage.Stage;

import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.ui.MainWindowUICreator;
import top.byteeeee.ipscanner.ui.UIBuilder;
import top.byteeeee.ipscanner.ui.theme.ThemeManager;

public class IPScanner extends Application {
    public static String APP_VERSION = "v1.3.2";

    @Override
    public void start(Stage primaryStage) {
        ThemeManager.init();
        primaryStage.setMinWidth(1244.0D);
        primaryStage.setMinHeight(666.0D);
        MainController controller = new MainController();
        UIBuilder uiBuilder = new MainWindowUICreator(controller);
        uiBuilder.setupUI(primaryStage);
    }

    public static void main(String[] args) {
        launch(args);
    }
}