local _, addon = ...

local eventFrame = CreateFrame("Frame")
local pendingAutomaticDisplay = false

local function showForPlayer()
    local classToken = addon.GetPlayerContext()
    if classToken == nil then
        return
    end

    local hasNewVersion = addon.HasUnseenAddonVersion()
    local hasLive = addon.HasUnseen(classToken, "live")
        or addon.HasUnseenShared("live")
    local hasPtr = addon.HasUnseen(classToken, "ptr")
        or addon.HasUnseenShared("ptr")
    if not hasNewVersion and not hasLive and not hasPtr then
        return
    end

    if InCombatLockdown() then
        pendingAutomaticDisplay = true
        return
    end

    pendingAutomaticDisplay = false
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
    if hasNewVersion then
        addon.MarkAddonVersionShown()
    end
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_SPECIALIZATION_CHANGED")
eventFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
eventFrame:SetScript("OnEvent", function(_, event, argument)
    if event == "ADDON_LOADED" and argument == addon.name then
        addon.InitializeState()
        addon.InitializeMinimapButton()
    elseif event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" then
        if event == "PLAYER_ENTERING_WORLD" then
            eventFrame:UnregisterEvent("PLAYER_ENTERING_WORLD")
        end

        showForPlayer()
    elseif event == "PLAYER_SPECIALIZATION_CHANGED"
        and argument == "player"
        and addon.window:IsShown()
    then
        addon.RefreshWindow()
    elseif event == "PLAYER_REGEN_ENABLED" and pendingAutomaticDisplay then
        showForPlayer()
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

    local classToken = addon.GetPlayerContext()
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
end
