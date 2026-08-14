on run arguments
  set volumeName to item 1 of arguments
  tell application "Finder"
    set targetDisk to first disk whose name is volumeName
    close every window whose target is targetDisk
  end tell
end run
