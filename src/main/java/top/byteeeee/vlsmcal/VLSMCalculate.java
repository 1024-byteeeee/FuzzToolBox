package top.byteeeee.vlsmcal;

import top.byteeeee.vlsmcal.calculator.IPConverter;
import top.byteeeee.vlsmcal.calculator.MaskCalculator;
import top.byteeeee.vlsmcal.calculator.NetworkCalculator;
import top.byteeeee.vlsmcal.calculator.WildcardMaskCalculator;
import top.byteeeee.vlsmcal.settings.Setting;
import top.byteeeee.vlsmcal.table.SubnetMaskTable;
import top.byteeeee.vlsmcal.utils.WindowUtils;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

@SuppressWarnings({"FieldMayBeFinal", "FieldCanBeLocal"})
public class VLSMCalculate extends JFrame implements ActionListener {

    public static final String SOFT_WARE_NAME = "VLSM-Calculator";
    public static Logger logger = Logger.getLogger(SOFT_WARE_NAME);
    private static ConcurrentHashMap<JButton, Runnable> buttonActions = new ConcurrentHashMap<>();
    public static final Image aNullIcon = new ImageIcon("null").getImage();
    private static JButton networkCalculatorButton;
    private static JButton maskCalculatorButton;
    private static JButton ipConverterButton;
    private static JButton wildcardMaskCalculatorButton;
    private static JButton subnetMaskTableButton;
    private static JButton softwareSettingButton;

    public VLSMCalculate() {
        Setting.loadSettings(this);
        setTitle("VLSM-Calculator v1.2.0 by 1024_byteeeee");
        setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        setLayout(new GridBagLayout());
        setResizable(true);
        setSize(789, 500);
        setIconImage(aNullIcon);

        WindowUtils.centerOnScreenTop(this);

        GridBagConstraints gbc = new GridBagConstraints();
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(10, 10, 10, 10);

        networkCalculatorButton = new JButton("网络和IP地址计算器");
        networkCalculatorButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 0;
        gbc.gridwidth = 2;
        add(networkCalculatorButton, gbc);

        maskCalculatorButton = new JButton("通过主机数量计算掩码");
        maskCalculatorButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 1;
        gbc.gridwidth = 2;
        add(maskCalculatorButton, gbc);

        ipConverterButton = new JButton("IP 进制转换器");
        ipConverterButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 2;
        gbc.gridwidth = 2;
        add(ipConverterButton, gbc);

        wildcardMaskCalculatorButton = new JButton("反掩码计算器");
        wildcardMaskCalculatorButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 3;
        gbc.gridwidth = 2;
        add(wildcardMaskCalculatorButton, gbc);

        subnetMaskTableButton = new JButton("子网掩码对照表");
        subnetMaskTableButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 4;
        gbc.gridwidth = 2;
        add(subnetMaskTableButton, gbc);

        softwareSettingButton = new JButton("软件设置");
        softwareSettingButton.addActionListener(this);
        gbc.gridx = 0;
        gbc.gridy = 5;
        gbc.gridwidth = 2;

        add(softwareSettingButton, gbc);
        addButtonActionsToMap();
        setVisible(true);
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            VLSMCalculate mainFrame = new VLSMCalculate();
            Setting.loadSettings(mainFrame);
            mainFrame.setVisible(true);
        });
    }

    @Override
    public void actionPerformed(ActionEvent e) {
        JButton button = (JButton) e.getSource();
        Runnable action = buttonActions.get(button);
        if (action != null) {
            SwingUtilities.invokeLater(action);
        }
    }

    private void addButtonActionsToMap() {
        buttonActions.put(networkCalculatorButton, NetworkCalculator::new);
        buttonActions.put(maskCalculatorButton, MaskCalculator::new);
        buttonActions.put(ipConverterButton, IPConverter::new);
        buttonActions.put(wildcardMaskCalculatorButton, WildcardMaskCalculator::new);
        buttonActions.put(subnetMaskTableButton, SubnetMaskTable::new);
        buttonActions.put(softwareSettingButton, () -> Setting.showSettingScreen(this));
    }
}
