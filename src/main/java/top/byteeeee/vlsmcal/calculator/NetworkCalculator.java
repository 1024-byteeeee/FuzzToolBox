package top.byteeeee.vlsmcal.calculator;

import top.byteeeee.vlsmcal.VLSMCalculate;
import top.byteeeee.vlsmcal.utils.KeyListenerUtils;
import top.byteeeee.vlsmcal.utils.WindowUtils;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.net.InetAddress;
import java.net.UnknownHostException;

@SuppressWarnings({"FieldMayBeFinal", "FieldCanBeLocal"})
public class NetworkCalculator extends JFrame implements ActionListener {

    private JTextField ipAddressField, subnetMaskField;
    private JLabel ipAddressLabel, subnetMaskLabel;
    private JButton calculateButton;
    private JTextArea resultArea;

    public NetworkCalculator() {
        setTitle("网络和IP地址计算器");
        setSize(888, 666);
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new GridBagLayout());
        setResizable(true);
        setIconImage(VLSMCalculate.aNullIcon);

        WindowUtils.centerOnScreen(this);

        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        ipAddressLabel = new JLabel("IP 地址:");
        gbc.gridx = 0;
        gbc.gridy = 0;
        add(ipAddressLabel, gbc);

        ipAddressField = new JTextField();
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.gridwidth = 2;
        add(ipAddressField, gbc);

        subnetMaskLabel = new JLabel("子网掩码:");
        gbc.gridx = 0;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        add(subnetMaskLabel, gbc);

        subnetMaskField = new JTextField();
        gbc.gridx = 1;
        gbc.gridy = 1;
        gbc.gridwidth = 2;
        add(subnetMaskField, gbc);

        calculateButton = new JButton("计算");
        calculateButton.addActionListener(this);
        gbc.gridx = 1;
        gbc.gridy = 2;
        gbc.gridwidth = 1;
        add(calculateButton, gbc);

        KeyListenerUtils.addEnterKeyListener(calculateButton, ipAddressField, subnetMaskField);

        resultArea = new JTextArea(6, 30);
        resultArea.setEditable(false);
        JScrollPane scrollPane = new JScrollPane(resultArea);
        gbc.gridx = 0;
        gbc.gridy = 3;
        gbc.gridwidth = 3;
        gbc.fill = GridBagConstraints.BOTH;
        add(scrollPane, gbc);

        setVisible(true);
    }

    @Override
    public void actionPerformed(ActionEvent e) {
        if (e.getSource() == calculateButton) {
            String ipAddress = ipAddressField.getText();
            String subnetMaskInput = subnetMaskField.getText();
            String subnetMask;
            int prefixLength;

            if (!ipAddress.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")) {
                JOptionPane.showMessageDialog(this, "IP地址格式错误", "错误", JOptionPane.ERROR_MESSAGE);
                return;
            }

            if (subnetMaskInput.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")) {
                subnetMask = subnetMaskInput;
                prefixLength = dottedDecimalToPrefix(subnetMask);
            } else if (subnetMaskInput.matches("\\d{1,2}")) {
                try {
                    prefixLength = Integer.parseInt(subnetMaskInput);
                    if (prefixLength < 0 || prefixLength > 32) {
                        throw new NumberFormatException();
                    }
                    subnetMask = prefixToDottedDecimal(prefixLength);
                } catch (NumberFormatException ex) {
                    JOptionPane.showMessageDialog(this, "子网掩码格式错误", "错误", JOptionPane.ERROR_MESSAGE);
                    return;
                }
            } else {
                JOptionPane.showMessageDialog(this, "子网掩码格式错误", "错误", JOptionPane.ERROR_MESSAGE);
                return;
            }

            try {
                InetAddress ip = InetAddress.getByName(ipAddress);
                InetAddress subnet = InetAddress.getByName(subnetMask);

                byte[] ipBytes = ip.getAddress();
                byte[] subnetBytes = subnet.getAddress();

                byte[] networkAddress = new byte[4];
                byte[] broadcastAddress = new byte[4];

                for (int i = 0; i < 4; i++) {
                    networkAddress[i] = (byte) (ipBytes[i] & subnetBytes[i]);
                    broadcastAddress[i] = (byte) (networkAddress[i] | ~subnetBytes[i]);
                }

                InetAddress firstHost = InetAddress.getByAddress(incrementByteArray(networkAddress.clone()));
                InetAddress lastHost = InetAddress.getByAddress(decrementByteArray(broadcastAddress.clone()));

                int availableHosts = (int) Math.pow(2, 32 - prefixLength) - 2;

                String result =
                    "网络地址: " + InetAddress.getByAddress(networkAddress).getHostAddress() + "\n" +
                    "广播地址: " + InetAddress.getByAddress(broadcastAddress).getHostAddress() + "\n" +
                    "第一个可用主机地址: " + firstHost.getHostAddress() + "\n" +
                    "最后一个可用主机地址: " + lastHost.getHostAddress() + "\n" +
                    "子网掩码: " + subnetMask + "\n" +
                    "可用地址数量: " + availableHosts;

                resultArea.setText(result);

            } catch (UnknownHostException ex) {
                JOptionPane.showMessageDialog(this, "请输入有效的IP地址和子网掩码", "错误", JOptionPane.ERROR_MESSAGE);
            }
        }
    }


    private String prefixToDottedDecimal(int prefix) {
        int mask = 0xffffffff << (32 - prefix);
        int octet1 = (mask >> 24) & 255;
        int octet2 = (mask >> 16) & 255;
        int octet3 = (mask >> 8) & 255;
        int octet4 = mask & 255;
        return octet1 + "." + octet2 + "." + octet3 + "." + octet4;
    }

    private int dottedDecimalToPrefix(String dottedDecimal) {
        String[] parts = dottedDecimal.split("\\.");
        int prefix = 0;
        for (String part : parts) {
            int byteValue = Integer.parseInt(part);
            while (byteValue > 0) {
                prefix += (byteValue & 1);
                byteValue >>= 1;
            }
        }
        return prefix;
    }

    private byte[] incrementByteArray(byte[] bytes) {
        for (int i = bytes.length - 1; i >= 0; i--) {
            if (bytes[i] == (byte) 255) {
                bytes[i] = 0;
            } else {
                bytes[i]++;
                break;
            }
        }
        return bytes;
    }

    private byte[] decrementByteArray(byte[] bytes) {
        for (int i = bytes.length - 1; i >= 0; i--) {
            if (bytes[i] == 0) {
                bytes[i] = (byte) 255;
            } else {
                bytes[i]--;
                break;
            }
        }
        return bytes;
    }
}
