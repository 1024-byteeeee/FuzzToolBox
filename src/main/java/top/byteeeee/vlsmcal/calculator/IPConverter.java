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
public class IPConverter extends JFrame implements ActionListener {

    private JTextField ipAddressField;
    private JButton calculateButton;
    private JTextArea resultArea;

    public IPConverter() {
        setTitle("IP 进制转换器");
        setSize(888, 666);
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new GridBagLayout());
        setResizable(true);
        setIconImage(VLSMCalculate.aNullIcon);

        WindowUtils.centerOnScreen(this);

        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        JLabel ipAddressLabel = new JLabel("点分十进制IP地址:");
        gbc.gridx = 0;
        gbc.gridy = 0;
        add(ipAddressLabel, gbc);

        ipAddressField = new JTextField();
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.gridwidth = 2;
        add(ipAddressField, gbc);

        calculateButton = new JButton("计算");
        calculateButton.addActionListener(this);
        gbc.gridx = 1;
        gbc.gridy = 1;
        gbc.gridwidth = 1;
        add(calculateButton, gbc);

        KeyListenerUtils.addEnterKeyListener(calculateButton, ipAddressField);

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
            String ipAddress = ipAddressField.getText();

            try {
                InetAddress inetAddress = InetAddress.getByName(ipAddress);
                byte[] ipAddressBytes = inetAddress.getAddress();

                String ip = inetAddress.getHostAddress();
                String binaryIP = convertToBinary(ipAddressBytes);
                String hexIP = convertToHexadecimal(ipAddressBytes);
                String decimalIP = convertToDecimal(ipAddressBytes);
                String result = "IP：" + ip + "\n" + "二进制: " + binaryIP + "\n" + "十六进制: " + hexIP + "\n" + "十进制: " + decimalIP;

                resultArea.setText(result);

            } catch (UnknownHostException ex) {
                JOptionPane.showMessageDialog(this, "请输入有效的IP地址", "错误", JOptionPane.ERROR_MESSAGE);
            }
        }
    }

    private String convertToBinary(byte[] ipAddressBytes) {
        StringBuilder binaryIP = new StringBuilder();
        for (byte octet : ipAddressBytes) {
            String binaryString = Integer.toBinaryString(octet & 0xFF);
            binaryIP.append(String.format("%8s", binaryString).replace(' ', '0')).append(".");
        }
        return binaryIP.substring(0, binaryIP.length() - 1);
    }

    private String convertToHexadecimal(byte[] ipAddressBytes) {
        StringBuilder hexIP = new StringBuilder();
        for (byte octet : ipAddressBytes) {
            hexIP.append(String.format("%02X", octet)).append(".");
        }
        return hexIP.substring(0, hexIP.length() - 1);
    }

    private String convertToDecimal(byte[] ipAddressBytes) {
        long decimalIP = 0;
        for (byte octet : ipAddressBytes) {
            decimalIP = (decimalIP << 8) | (octet & 0xFF);
        }
        return String.valueOf(decimalIP);
    }
}
