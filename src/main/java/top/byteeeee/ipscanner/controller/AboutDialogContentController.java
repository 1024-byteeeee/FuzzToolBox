package top.byteeeee.ipscanner.controller;

import javafx.fxml.FXML;
import javafx.scene.control.Label;
import top.byteeeee.ipscanner.IPScanner;

public class AboutDialogContentController {
    @FXML private Label versionLabel;

    @FXML
    private void initialize() {
        versionLabel.setText("版本：" + IPScanner.APP_VERSION);
    }
}