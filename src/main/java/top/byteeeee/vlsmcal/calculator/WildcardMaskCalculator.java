package top.byteeeee.vlsmcal.calculator;

import top.byteeeee.vlsmcal.VLSMCalculate;
import top.byteeeee.vlsmcal.utils.KeyListenerUtils;
import top.byteeeee.vlsmcal.utils.WindowUtils;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;

@SuppressWarnings({"FieldMayBeFinal", "FieldCanBeLocal"})
public class WildcardMaskCalculator extends JFrame implements ActionListener {

    private JTextField subnetMaskField;
    private JButton calculateButton;
    private JTextArea resultArea;

    public WildcardMaskCalculator() {
        setTitle("反掩码计算器");
        setSize(666, 450);
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new GridBagLayout());
        setResizable(true);
        setIconImage(VLSMCalculate.aNullIcon);

        WindowUtils.centerOnScreen(this);

        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        JLabel subnetMaskLabel = new JLabel("子网掩码:");
        gbc.gridx = 0;
        gbc.gridy = 0;
        add(subnetMaskLabel, gbc);

        subnetMaskField = new JTextField();
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.gridwidth = 2;
        add(subnetMaskField, gbc);

        calculateButton = new JButton("计算");
        calculateButton.addActionListener(this);
        gbc.gridx = 1;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        add(calculateButton, gbc);

        KeyListenerUtils.addEnterKeyListener(calculateButton, subnetMaskField);

        resultArea = new JTextArea(2, 25);
        resultArea.setEditable(false);
        JScrollPane scrollPane = new JScrollPane(resultArea);
        gbc.gridx = 0;
        gbc.gridy = 2;
        gbc.gridwidth = 3;
        gbc.fill = GridBagConstraints.BOTH;
        add(scrollPane, gbc);
        setVisible(true);
    }

    @Override
    public void actionPerformed(ActionEvent e) {
        if (e.getSource().equals(calculateButton)) {
            String subnetMaskInput = subnetMaskField.getText();
            if (!subnetMaskInput.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")) {
                JOptionPane.showMessageDialog(this, "子网掩码格式错误", "错误", JOptionPane.ERROR_MESSAGE);
                return;
            }
            String wildcardMask = calculateWildcardMask(subnetMaskInput);
            resultArea.setText(
                "子网掩码: " + subnetMaskInput + "\n" +
                "反掩码: " + wildcardMask
            );
        }
    }

    private String calculateWildcardMask(String subnetMask) {
        String[] parts = subnetMask.split("\\.");
        int[] maskBytes = new int[4];
        for (int i = 0; i < 4; i++) {
            maskBytes[i] = Integer.parseInt(parts[i]);
        }
        int[] wildcardBytes = new int[4];
        for (int i = 0; i < 4; i++) {
            wildcardBytes[i] = 255 - maskBytes[i];
        }
        return wildcardBytes[0] + "." + wildcardBytes[1] + "." + wildcardBytes[2] + "." + wildcardBytes[3];
    }
}
