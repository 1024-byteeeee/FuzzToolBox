module top.byteeeee.ipscanner {
    requires javafx.controls;
    requires javafx.fxml;
    requires darklaf.core;

    exports top.byteeeee.ipscanner;
    exports top.byteeeee.ipscanner.ui;
    exports top.byteeeee.ipscanner.controller;
    exports top.byteeeee.ipscanner.model;
    exports top.byteeeee.ipscanner.ui.theme;

    opens top.byteeeee.ipscanner to javafx.fxml;
    opens top.byteeeee.ipscanner.model to javafx.base, javafx.fxml;
    opens top.byteeeee.ipscanner.ui to javafx.fxml;
    opens top.byteeeee.ipscanner.controller to javafx.fxml;
    opens top.byteeeee.ipscanner.factory to javafx.fxml;
}