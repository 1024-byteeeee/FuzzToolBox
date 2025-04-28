package top.byteeeee.vlsmcal.calculator;

import top.byteeeee.vlsmcal.VLSMCalculate;
import top.byteeeee.vlsmcal.utils.KeyListenerUtils;
import top.byteeeee.vlsmcal.utils.WindowUtils;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;

@SuppressWarnings({"FieldMayBeFinal", "FieldCanBeLocal"})
public class MaskCalculator extends JFrame implements ActionListener {

    private JTextField hostsRequiredField;
    private JLabel hostsRequiredLabel;
    private JButton calculateButton;
    private JTextArea resultArea;

    public MaskCalculator() {
        setTitle("通过主机数量计算掩码");
        setSize(888, 666);
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new GridBagLayout());
        setResizable(true);
        setIconImage(VLSMCalculate.aNullIcon);

        WindowUtils.centerOnScreen(this);

        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        hostsRequiredLabel = new JLabel("需要的主机数:");
        gbc.gridx = 0;
        gbc.gridy = 0;
        add(hostsRequiredLabel, gbc);

        hostsRequiredField = new JTextField();
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.gridwidth = 2;
        add(hostsRequiredField, gbc);

        calculateButton = new JButton("计算");
        calculateButton.addActionListener(this);
        gbc.gridx = 1;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        add(calculateButton, gbc);

        KeyListenerUtils.addEnterKeyListener(calculateButton, hostsRequiredField);

        resultArea = new JTextArea(4, 30);
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
        if (e.getSource() == calculateButton) {
            String hostsRequiredStr = hostsRequiredField.getText();

            try {
                int hostsRequired = Integer.parseInt(hostsRequiredStr);
                int subnetMaskBits = calculateSubnetMask(hostsRequired);
                String calculatedSubnetMask = generateSubnetMask(subnetMaskBits);
                String cidrSubnetMask = generateCIDRSubnetMask(subnetMaskBits);
                int availableHosts = calculateAvailableHosts(subnetMaskBits);

                String result =
                    "需要的主机数: " + hostsRequired + "\n" +
                    "子网掩码（点分十进制）: " + calculatedSubnetMask + "\n" +
                    "子网掩码（CIDR格式）: " + cidrSubnetMask + "\n" +
                    "可用主机数量: " + availableHosts;

                resultArea.setText(result);

            } catch (NumberFormatException ex) {
                JOptionPane.showMessageDialog(this, "请输入有效的主机数目", "错误", JOptionPane.ERROR_MESSAGE);
            }
        }
    }

    private int calculateSubnetMask(int hostsRequired) {
        int bits = 0;
        while ((1 << bits) - 2 < hostsRequired) {
            bits++;
        }
        return 32 - bits;
    }

    private String generateSubnetMask(int subnetMaskBits) {
        StringBuilder subnetMask = new StringBuilder();
        for (int i = 0; i < 4; i++) {
            int octetValue = 0;
            if (subnetMaskBits >= 8) {
                octetValue = 255;
                subnetMaskBits -= 8;
            } else {
                for (int j = 7; j >= 8 - subnetMaskBits; j--) {
                    octetValue |= (1 << j);
                }
                subnetMaskBits = 0;
            }
            subnetMask.append(octetValue);
            if (i < 3) {
                subnetMask.append('.');
            }
        }
        return subnetMask.toString();
    }

    private String generateCIDRSubnetMask(int subnetMaskBits) {
        return "/" + subnetMaskBits;
    }

    private int calculateAvailableHosts(int subnetMaskBits) {
        return (int) Math.pow(2, 32 - subnetMaskBits) - 2;
    }
}
