package top.byteeeee.ipscanner.impl;

import javafx.application.Platform;
import javafx.collections.ObservableList;
import javafx.scene.control.Alert;
import javafx.stage.FileChooser;
import javafx.stage.Window;

import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.helper.AlertHelper;
import top.byteeeee.ipscanner.model.ScanResult;
import top.byteeeee.ipscanner.service.ExportService;

import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public record ExportImpl(MainController controller) implements ExportService {
    @Override
    public void exportResults(ObservableList<ScanResult> data, Window window) {
        if (data.isEmpty()) {
            AlertHelper.showAlert("警告", "没有可导出的扫描结果", Alert.AlertType.WARNING);
            return;
        }

        FileChooser fileChooser = new FileChooser();
        fileChooser.setTitle("保存结果");

        FileChooser.ExtensionFilter csvFilter = new FileChooser.ExtensionFilter("CSV文件 (*.csv)", "*.csv");
        FileChooser.ExtensionFilter txtFilter = new FileChooser.ExtensionFilter("文本文件 (*.txt)", "*.txt");
        fileChooser.getExtensionFilters().addAll(csvFilter, txtFilter);
        fileChooser.setSelectedExtensionFilter(csvFilter);

        File file = fileChooser.showSaveDialog(window);
        if (file == null) return;

        try {
            FileChooser.ExtensionFilter selectedFilter = fileChooser.getSelectedExtensionFilter();
            if (selectedFilter == null) {
                AlertHelper.showAlert("错误", "未选择文件类型", Alert.AlertType.ERROR);
                return;
            }

            String extension = selectedFilter.getExtensions().getFirst().replace("*.", ".");
            String fileName = file.getName();

            if (!fileName.toLowerCase().endsWith(extension.toLowerCase())) {
                file = new File(file.getParent(), fileName + extension);
            }

            File parentDir = file.getParentFile();
            if (parentDir != null) {
                if (!parentDir.exists() && !parentDir.mkdirs()) {
                    AlertHelper.showAlert("错误", "无法创建目录: " + parentDir.getAbsolutePath(), Alert.AlertType.ERROR);
                    return;
                }
                if (!parentDir.canWrite()) {
                    AlertHelper.showAlert("错误", "目录不可写: " + parentDir.getAbsolutePath(), Alert.AlertType.ERROR);
                    return;
                }
            }

            try (PrintWriter writer = new PrintWriter(file, StandardCharsets.UTF_8)) {
                boolean isCSV = selectedFilter == csvFilter;
                writer.println(isCSV ? "序号,IP地址,状态,响应时间,MAC地址,主机名" : "序号\tIP地址\t状态\t响应时间\tMAC地址\t主机名");

                for (ScanResult result : data) {
                    String line = isCSV ?
                        String.format("\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\"",
                            result.getIndex().replace("\"", "\"\""),
                            result.getIp().replace("\"", "\"\""),
                            result.getStatus().replace("\"", "\"\""),
                            result.getResponseTime().replace("\"", "\"\""),
                            result.getMacAddr().replace("\"", "\"\""),
                            result.getHostname().replace("\"", "\"\"")) :
                        String.format("%s\t%s\t%s\t%s\t%s\t%s",
                            result.getIndex(),
                            result.getIp(),
                            result.getStatus(),
                            result.getResponseTime(),
                            result.getMacAddr(),
                            result.getHostname());
                    writer.println(line);
                }
                File finalFile = file;
                Platform.runLater(() -> AlertHelper.showAlert("成功", "结果已成功导出至:\n" + finalFile.getAbsolutePath(), Alert.AlertType.INFORMATION));
            }
        } catch (Exception e) {
            Platform.runLater(() -> {
                Alert errorAlert = new Alert(Alert.AlertType.ERROR);
                errorAlert.setTitle("错误");
                errorAlert.setHeaderText("导出过程中发生错误");
                errorAlert.setContentText("错误类型: " + e.getClass().getSimpleName() + "\n错误信息: " + e.getMessage());
                errorAlert.showAndWait();
            });
        }
    }
}
