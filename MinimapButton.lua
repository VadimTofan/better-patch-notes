local _, addon = ...

local BUTTON_SIZE = 32
local DEFAULT_ANGLE = 220

local button = CreateFrame("Button", "BetterPatchNotesMinimapButton", Minimap)
button:SetSize(BUTTON_SIZE, BUTTON_SIZE)
button:SetFrameStrata("MEDIUM")
button:SetFrameLevel(Minimap:GetFrameLevel() + 8)
button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
button:RegisterForDrag("LeftButton")
button:Hide()

local icon = button:CreateTexture(nil, "BACKGROUND")
icon:SetTexture("Interface\\Icons\\INV_Misc_Note_05")
icon:SetSize(20, 20)
icon:SetPoint("CENTER")

local border = button:CreateTexture(nil, "OVERLAY")
border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
border:SetSize(54, 54)
border:SetPoint("TOPLEFT")

local highlight = button:CreateTexture(nil, "HIGHLIGHT")
highlight:SetTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
highlight:SetBlendMode("ADD")
highlight:SetAllPoints()

local function minimapRadius()
    local diameter = math.max(Minimap:GetWidth(), Minimap:GetHeight())

    return (diameter / 2) + (BUTTON_SIZE / 3)
end

local function setPosition(angle)
    local radians = math.rad(angle)
    local radius = minimapRadius()
    local x = math.cos(radians) * radius
    local y = math.sin(radians) * radius

    button:ClearAllPoints()
    button:SetPoint("CENTER", Minimap, "CENTER", x, y)
end

local function openWindow()
    local classToken = addon.GetPlayerContext()
    if classToken == nil then
        return
    end

    addon.ShowWindow(addon.SelectInitialChannel(classToken))
end

local function setVisible(visible)
    addon.db.minimap.hidden = not visible
    if visible then
        setPosition(addon.db.minimap.angle)
        button:Show()
        return
    end

    button:Hide()
end

local function showContextMenu()
    MenuUtil.CreateContextMenu(button, function(_, rootDescription)
        rootDescription:CreateButton(addon.GetText("OPEN_ADDON"), openWindow)
        rootDescription:CreateButton(
            addon.GetText("HIDE_MINIMAP_BUTTON"),
            function()
                setVisible(false)
            end
        )
    end)
end

local function updatePositionFromCursor()
    local cursorX, cursorY = GetCursorPosition()
    local scale = UIParent:GetEffectiveScale()
    local centerX, centerY = Minimap:GetCenter()
    if centerX == nil or centerY == nil or scale == 0 then
        return
    end

    cursorX = cursorX / scale
    cursorY = cursorY / scale
    local angle = math.deg(math.atan2(cursorY - centerY, cursorX - centerX))
    addon.db.minimap.angle = angle
    setPosition(angle)
end

button:SetScript("OnClick", function(_, mouseButton)
    if mouseButton == "LeftButton" then
        openWindow()
    elseif mouseButton == "RightButton" then
        showContextMenu()
    end
end)
button:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", updatePositionFromCursor)
end)
button:SetScript("OnDragStop", function(self)
    self:SetScript("OnUpdate", nil)
end)
button:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(addon.GetText("TITLE"))
    GameTooltip:Show()
end)
button:SetScript("OnLeave", function()
    GameTooltip:Hide()
end)

function addon.InitializeMinimapButton()
    local angle = addon.db.minimap.angle or DEFAULT_ANGLE
    addon.db.minimap.angle = angle
    setPosition(angle)

    if addon.db.minimap.hidden then
        button:Hide()
    else
        button:Show()
    end
end

function addon.ToggleMinimapButton()
    setVisible(addon.db.minimap.hidden)
end

addon.minimapButton = button
