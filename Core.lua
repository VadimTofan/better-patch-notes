local _, addon = ...

local eventFrame = CreateFrame("Frame")
local pendingAutomaticDisplay = false

local function showForNewVersion()
    local hasNewVersion = addon.HasUnseenAddonVersion()
    if not hasNewVersion then
        return
    end

    local classToken = addon.GetPlayerContext()
    if classToken == nil then
        return
    end

    if InCombatLockdown() then
        pendingAutomaticDisplay = true
        return
    end

    pendingAutomaticDisplay = false
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
    if addon.window:IsShown() then
        addon.MarkAddonVersionShown()
    end
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_SPECIALIZATION_CHANGED")
eventFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
eventFrame:SetScript("OnEvent", function(_, event, argument)
    if event == "ADDON_LOADED" and argument == addon.name then
        addon.InitializeState()
        addon.InitializeMinimapButton()
    elseif event == "PLAYER_ENTERING_WORLD" then
        C_Timer.After(1, showForNewVersion)
    elseif event == "PLAYER_SPECIALIZATION_CHANGED"
        and argument == "player"
        and addon.window:IsShown()
    then
        addon.RefreshWindow()
    elseif event == "PLAYER_REGEN_ENABLED" and pendingAutomaticDisplay then
        showForNewVersion()
    end
end)

SLASH_BETTERPATCHNOTES1 = "/bpn"
SLASH_BETTERPATCHNOTES2 = "/betterpatchnotes"
SlashCmdList.BETTERPATCHNOTES = function(message)
    message = (message or ""):match("^%s*(.-)%s*$"):lower()
    if message == "minimap" then
        addon.ToggleMinimapButton()
        return
    end

    if message == "version" then
        local lastShownVersion = addon.db.lastShownAddonVersion
        if lastShownVersion == "" then
            lastShownVersion = "none"
        end

        print(string.format(
            "Better Patch Notes: installed %s; last shown %s",
            addon.version,
            lastShownVersion
        ))
        showForNewVersion()
        return
    end

    local classToken = addon.GetPlayerContext()
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
end
