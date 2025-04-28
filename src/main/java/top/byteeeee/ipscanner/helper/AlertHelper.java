package top.byteeeee.ipscanner.helper;

import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.scene.control.Alert;
import javafx.scene.control.Button;
import javafx.scene.control.ButtonType;
import javafx.scene.image.Image;
import javafx.scene.layout.VBox;
import javafx.stage.Modality;
import javafx.stage.Stage;

import top.byteeeee.ipscanner.IPScanner;
import top.byteeeee.ipscanner.controller.ThemeDialogController;
import top.byteeeee.ipscanner.ui.MainWindowUICreator;
import top.byteeeee.ipscanner.ui.theme.ThemeManager;

import java.io.IOException;

public class AlertHelper {
    public static void showAlert(String title, String content, Alert.AlertType type) {
        Alert alert = new Alert(type);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(content);
        applyThemeToDialog(alert);
        applyAlertWindowIcon(alert);
        alert.showAndWait();
    }

    public static void showThemeDialog(Scene mainScene) {
        try {
            Stage dialog = new Stage();
            dialog.initModality(Modality.APPLICATION_MODAL);
            dialog.setTitle("选择主题");
            FXMLLoader loader = new FXMLLoader(AlertHelper.class.getResource("/fxml/ThemeDialog.fxml"));
            Scene dialogScene = new Scene(loader.load(), 250, 150);
            ThemeDialogController controller = loader.getController();
            controller.init(mainScene, dialog);
            ThemeManager.applyTheme(dialogScene, ThemeManager.getCurrentTheme());
            dialog.setScene(dialogScene);
            dialog.getIcons().add(new Image(MainWindowUICreator.ICON_PATH));
            dialog.show();
        } catch (IOException e) {
            showAlert("错误", "无法加载主题选择对话框: " + e.getMessage(), Alert.AlertType.ERROR);
        }
    }

    public static void showConfirmAlert(String title, String content, Runnable confirmAction) {
        Alert alert = new Alert(Alert.AlertType.CONFIRMATION);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(content);
        applyThemeToDialog(alert);
        applyAlertWindowIcon(alert);
        alert.showAndWait().ifPresent(response -> {
            if (response == ButtonType.OK) {
                confirmAction.run();
            }
        });
    }

    public static void showAboutDialog() {
        try {
            Alert alert = new Alert(Alert.AlertType.INFORMATION);
            alert.setTitle("关于本软件");
            alert.setHeaderText("IP-Scanner " + IPScanner.APP_VERSION);
            FXMLLoader loader = new FXMLLoader(AlertHelper.class.getResource("/fxml/AboutDialogContent.fxml"));
            VBox content = loader.load();
            alert.getDialogPane().setContent(content);
            alert.getDialogPane().setPrefSize(400, 245);
            applyThemeToDialog(alert);
            applyAlertWindowIcon(alert);
            alert.showAndWait();
        } catch (IOException e) {
            showAlert("错误", "无法加载关于对话框内容: " + e.getMessage(), Alert.AlertType.ERROR);
        }
    }

    public static void showThemeError(String cssPath) {
        Alert alert = new Alert(Alert.AlertType.ERROR);
        alert.setTitle("主题错误");
        alert.setHeaderText(null);
        alert.setContentText("找不到主题文件: " + cssPath);
        applyThemeToDialog(alert);
        applyAlertWindowIcon(alert);
        alert.showAndWait();
    }

    private static void applyThemeToDialog(Alert alert) {
        Scene alertScene = alert.getDialogPane().getScene();
        ThemeManager.applyTheme(alertScene, ThemeManager.getCurrentTheme());
        alert.getDialogPane().getButtonTypes().forEach(buttonType -> {
            Button button = (Button) alert.getDialogPane().lookupButton(buttonType);
            if (button != null) {
                button.getStyleClass().add("control-button");
            }
        });
    }

    private static void applyAlertWindowIcon(Alert alert) {
        Stage stage = (Stage) alert.getDialogPane().getScene().getWindow();
        stage.getIcons().add(new Image(MainWindowUICreator.ICON_PATH));
    }
}
