package top.byteeeee.vlsmcal.utils;

import javax.swing.*;
import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;

public class KeyListenerUtils {
    public static void addEnterKeyListener(JButton button, JTextField... textFields) {
        for (JTextField textField : textFields) {
            textField.addKeyListener(new KeyAdapter() {
                @Override
                public void keyPressed(KeyEvent e) {
                    if (e.getKeyCode() == KeyEvent.VK_ENTER) {
                        button.doClick();
                    }
                }
            });
        }
    }
}
