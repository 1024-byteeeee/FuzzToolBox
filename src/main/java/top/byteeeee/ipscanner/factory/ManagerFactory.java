package top.byteeeee.ipscanner.factory;

import top.byteeeee.ipscanner.controller.MainController;
import top.byteeeee.ipscanner.service.ExportService;
import top.byteeeee.ipscanner.service.ScanService;
import top.byteeeee.ipscanner.impl.ExportImpl;
import top.byteeeee.ipscanner.impl.ScanImpl;

public class ManagerFactory {
    public static ScanService createScanService(MainController controller) {
        return new ScanImpl(controller);
    }

    public static ExportService createExportService(MainController controller) {
        return new ExportImpl(controller);
    }
}
