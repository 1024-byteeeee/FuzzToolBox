package top.byteeeee.ipscanner.service;

import javafx.collections.ObservableList;
import javafx.stage.Window;

import top.byteeeee.ipscanner.model.ScanResult;

public interface ExportService {
    void exportResults(ObservableList<ScanResult> data, Window window);
}
