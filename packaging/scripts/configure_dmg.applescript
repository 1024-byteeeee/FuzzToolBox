on run arguments
  set volumeName to item 1 of arguments
  set applicationName to item 2 of arguments
  set windowRight to (item 3 of arguments) as integer
  set windowBottom to (item 4 of arguments) as integer
  set finderIconSize to (item 5 of arguments) as integer
  set applicationX to (item 6 of arguments) as integer
  set applicationY to (item 7 of arguments) as integer
  set applicationsX to (item 8 of arguments) as integer
  set applicationsY to (item 9 of arguments) as integer

  tell application "Finder"
    set targetDisk to first disk whose name is volumeName
    tell targetDisk
      open
      set current view of container window to icon view
      set toolbar visible of container window to false
      set statusbar visible of container window to false
      set pathbar visible of container window to false
      set the bounds of container window to {120, 120, windowRight, windowBottom}
      set opts to the icon view options of container window
      set arrangement of opts to not arranged
      set icon size of opts to finderIconSize
      set text size of opts to 14
      set background picture of opts to file ".background:background.png"
      set position of item applicationName to {applicationX, applicationY}
      set position of item "Applications" to {applicationsX, applicationsY}
      close
      open
      update without registering applications
      delay 2
    end tell
  end tell
end run
