package top.byteeeee.ipscanner.controller;

import com.github.weisj.darklaf.LafManager;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.stage.Window;

import top.byteeeee.ipscanner.factory.ManagerFactory;
import top.byteeeee.ipscanner.helper.AlertHelper;
import top.byteeeee.ipscanner.model.ScanResult;
import top.byteeeee.ipscanner.service.ExportService;
import top.byteeeee.ipscanner.service.ScanService;
import top.byteeeee.ipscanner.util.IPUtils;
import top.byteeeee.vlsmcal.VLSMCalculate;

import javax.swing.*;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class MainController {
    @FXML private MenuItem themeItem;
    @FXML private MenuItem aboutItem;
    @FXML private TextField startIPField;
    @FXML private TextField endIPField;
    @FXML private TextField threadsField;
    @FXML private TextField timeoutField;
    @FXML private Button startButton;
    @FXML private Button stopButton;
    @FXML private Button exportButton;
    @FXML private TableView<ScanResult> tableView;
    @FXML private ProgressBar progressBar;
    @FXML private Label statusLabel;
    @FXML private MenuItem vlsmCalculate;

    private final ObservableList<ScanResult> data = FXCollections.observableArrayList();
    private final ScanService scanService;
    private final ExportService exportService;

    public MainController() {
        this.scanService = ManagerFactory.createScanService(this);
        this.exportService = ManagerFactory.createExportService(this);
    }

    @FXML
    public void initialize() {
        threadsField.setText(String.valueOf(Runtime.getRuntime().availableProcessors() * 5));
        tableView.setItems(data);
        setupEventHandlers();
    }

    private void setupEventHandlers() {
        startButton.setOnAction(event -> startScan());
        stopButton.setOnAction(event -> stopScan());
        exportButton.setOnAction(event -> exportResults());
        themeItem.setOnAction(event -> AlertHelper.showThemeDialog(startButton.getScene()));
        aboutItem.setOnAction(event -> AlertHelper.showAboutDialog());
        vlsmCalculate.setOnAction(event -> openVLSMCalculator());
    }

    private void startScan() {
        startButton.setDisable(true);
        exportButton.setDisable(true);
        resetScan();
        try {
            String startIP = startIPField.getText();
            String endIP = endIPField.getText();

            if (!IPUtils.isValidIPv4(startIP) || !IPUtils.isValidIPv4(endIP)) {
                AlertHelper.showAlert("错误", "IP地址格式错误，请填写正确的IPv4地址", Alert.AlertType.ERROR);
                startButton.setDisable(false);
                return;
            }

            long startIPLong = IPUtils.ipToLong(InetAddress.getByName(startIP));
            long endIPLong = IPUtils.ipToLong(InetAddress.getByName(endIP));
            if (startIPLong > endIPLong) {
                AlertHelper.showAlert("输入错误", "起始IP不能大于结束IP", Alert.AlertType.ERROR);
                startButton.setDisable(false);
                return;
            }

            int threadCount = Integer.parseInt(threadsField.getText());
            int timeout = Integer.parseInt(timeoutField.getText());
            scanService.startScan(startIP, endIP, threadCount, timeout);
        } catch (IllegalArgumentException | UnknownHostException e) {
            AlertHelper.showAlert("输入错误", "请检查输入: " + e.getMessage(), Alert.AlertType.ERROR);
            startButton.setDisable(false);
        }
    }

    private void stopScan() {
        scanService.requestStopScan();
    }

    public boolean isScanning() {
        return startButton.isDisabled();
    }

    private void exportResults() {
        Window window = tableView.getScene().getWindow();
        exportService.exportResults(data, window);
    }

    private void resetScan() {
        data.clear();
        progressBar.setProgress(0);
        statusLabel.setText("就绪");
    }

    private void openVLSMCalculator() {
        new Thread(() -> SwingUtilities.invokeLater(() -> {
            try {
                VLSMCalculate vlsmFrame = new VLSMCalculate();
                vlsmFrame.setVisible(true);
            } catch (Exception ignored) {}
        })).start();
    }

    public Button getStartButton() {
        return startButton;
    }

    public Button getStopButton() {
        return stopButton;
    }

    public Button getExportButton() {
        return exportButton;
    }

    public ProgressBar getProgressBar() {
        return progressBar;
    }

    public Label getStatusLabel() {
        return statusLabel;
    }

    public ObservableList<ScanResult> getData() {
        return data;
    }

    static {
        LafManager.install();
    }
}
