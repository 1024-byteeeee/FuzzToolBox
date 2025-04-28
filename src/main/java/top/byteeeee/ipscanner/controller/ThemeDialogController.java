package top.byteeeee.ipscanner.controller;

import javafx.fxml.FXML;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.stage.Stage;

import top.byteeeee.ipscanner.ui.theme.ThemeManager;

public class ThemeDialogController {
    @FXML private Button lightButton;
    @FXML private Button darkButton;

    private Scene mainScene;
    private Stage dialogStage;

    public void init(Scene mainScene, Stage dialogStage) {
        this.mainScene = mainScene;
        this.dialogStage = dialogStage;
    }

    @FXML
    private void applyLightTheme() {
        ThemeManager.applyTheme(mainScene, "light-theme");
        dialogStage.close();
    }

    @FXML
    private void applyDarkTheme() {
        ThemeManager.applyTheme(mainScene, "dark-theme");
        dialogStage.close();
    }
}
