package top.byteeeee.vlsmcal.table;

import top.byteeeee.vlsmcal.VLSMCalculate;
import top.byteeeee.vlsmcal.utils.WindowUtils;

import javax.swing.*;
import javax.swing.table.DefaultTableCellRenderer;
import javax.swing.table.DefaultTableModel;
import java.awt.*;

public class SubnetMaskTable extends JFrame {
    public SubnetMaskTable() {
        setTitle("子网掩码对照表");
        setSize(650, 888);
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new BorderLayout());
        setResizable(true);
        setIconImage(VLSMCalculate.aNullIcon);

        WindowUtils.centerOnScreen(this);

        String[] columnNames = {"掩码", "位", "IP数"};
        DefaultTableModel model = new DefaultTableModel(columnNames, 0);

        generateSubnetMaskData(model);

        JTable table = new JTable(model) {
            @Override
            public boolean isCellEditable(int row, int column) {
                return false;
            }
        };
        table.setRowHeight(30);

        DefaultTableCellRenderer centerRenderer = new DefaultTableCellRenderer();
        centerRenderer.setHorizontalAlignment(JLabel.CENTER);
        for (int i = 0; i < table.getColumnCount(); i++) {
            table.getColumnModel().getColumn(i).setCellRenderer(centerRenderer);
        }

        JScrollPane scrollPane = new JScrollPane(table);

        add(scrollPane, BorderLayout.CENTER);
        setVisible(true);
    }

    private void generateSubnetMaskData(DefaultTableModel model) {
        for (int bits = 1; bits <= 32; bits++) {
            String mask = calculateSubnetMask(bits);
            long ipCount = (long) Math.pow(2, (32 - bits));
            model.addRow(new Object[]{mask, bits, ipCount});
        }
    }

    private String calculateSubnetMask(int bits) {
        int mask = 0xFFFFFFFF << (32 - bits);
        return String.format(
            "%d.%d.%d.%d",
            (mask >>> 24) & 0xFF,
            (mask >>> 16) & 0xFF,
            (mask >>> 8) & 0xFF,
            mask & 0xFF
        );
    }
}
