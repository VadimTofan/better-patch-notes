local _, addon = ...

local eventFrame = CreateFrame("Frame")
local pendingAutomaticDisplay = false

local function showForPlayer()
    local classToken = addon.GetPlayerContext()
    if classToken == nil then
        return
    end

    local hasLive = addon.HasUnseen(classToken, "live")
    local hasPtr = addon.HasUnseen(classToken, "ptr")
    if not hasLive and not hasPtr then
        return
    end

    if InCombatLockdown() then
        pendingAutomaticDisplay = true
        return
    end

    pendingAutomaticDisplay = false
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
end

eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("PLAYER_SPECIALIZATION_CHANGED")
eventFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
eventFrame:SetScript("OnEvent", function(_, event, argument)
    if event == "ADDON_LOADED" and argument == addon.name then
        addon.InitializeState()
    elseif event == "PLAYER_LOGIN" then
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
SlashCmdList.BETTERPATCHNOTES = function()
    local classToken = addon.GetPlayerContext()
    addon.ShowWindow(addon.SelectInitialChannel(classToken))
end
