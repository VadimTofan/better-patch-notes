local _, addon = ...

local CLASS_COUNT = 13
local CLASS_ICON_SIZE = 26
local CLASS_ICON_STEP = 31
local CLASS_ICON_START = 274

local frame = CreateFrame(
    "Frame",
    "BetterPatchNotesWindow",
    UIParent,
    "BackdropTemplate"
)
frame:SetSize(760, 650)
frame:SetFrameStrata("DIALOG")
frame:SetClampedToScreen(true)
frame:SetMovable(true)
frame:EnableMouse(true)
frame:SetBackdrop({
    bgFile = "Interface/Tooltips/UI-Tooltip-Background",
    edgeFile = "Interface/Tooltips/UI-Tooltip-Border",
    edgeSize = 14,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
frame:SetBackdropColor(0.035, 0.04, 0.055, 0.98)
frame:SetBackdropBorderColor(0.35, 0.42, 0.55, 1)
frame:Hide()

local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOPLEFT", frame, "TOPLEFT", 24, -20)
title:SetText(addon.GetText("TITLE"))

local closeButton = CreateFrame(
    "Button",
    nil,
    frame,
    "UIPanelCloseButton"
)
closeButton:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -4, -4)

local scrollFrame = CreateFrame(
    "ScrollFrame",
    nil,
    frame,
    "UIPanelScrollFrameTemplate"
)
scrollFrame:SetPoint("TOPLEFT", frame, "TOPLEFT", 24, -92)
scrollFrame:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -44, 24)

local content = CreateFrame("Frame", nil, scrollFrame)
content:SetSize(676, 1)
scrollFrame:SetScrollChild(content)

local tabs = {}
local classButtons = {}
local headerPool = {}
local notePool = {}
local collapsed = {}
local activeChannel = "live"
local selectedClassToken
local playerClassToken
local usedHeaders = 0
local usedNotes = 0

local function styleTab(button, selected)
    if selected then
        button:SetBackdropColor(0.12, 0.34, 0.58, 1)
        button.label:SetTextColor(1, 0.82, 0, 1)
    else
        button:SetBackdropColor(0.08, 0.09, 0.12, 1)
        button.label:SetTextColor(0.75, 0.78, 0.85, 1)
    end
end

local function CreateTab(channel, label, offset)
    local button = CreateFrame("Button", nil, frame, "BackdropTemplate")
    button:SetSize(116, 32)
    button:SetPoint("TOPLEFT", frame, "TOPLEFT", offset, -52)
    button:SetBackdrop({
        bgFile = "Interface/Tooltips/UI-Tooltip-Background",
        edgeFile = "Interface/Tooltips/UI-Tooltip-Border",
        edgeSize = 10,
    })
    button.label = button:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontNormal"
    )
    button.label:SetPoint("CENTER")
    button.label:SetText(label)
    button:SetScript("OnClick", function()
        activeChannel = channel
        addon.RefreshWindow()
    end)
    tabs[channel] = button

    return button
end

CreateTab("live", addon.GetText("LIVE"), 24)
CreateTab("ptr", addon.GetText("PTR"), 148)

local function setClassIcon(texture, classToken)
    local atlasName = "classicon-" .. classToken:lower()
    if C_Texture ~= nil
        and C_Texture.GetAtlasInfo ~= nil
        and C_Texture.GetAtlasInfo(atlasName) ~= nil
    then
        texture:SetAtlas(atlasName)
        return
    end

    local coordinates = CLASS_ICON_TCOORDS[classToken]
    texture:SetTexture(
        "Interface/GLUES/CHARACTERCREATE/UI-CHARACTERCREATE-CLASSES"
    )
    if coordinates ~= nil then
        texture:SetTexCoord(
            coordinates[1],
            coordinates[2],
            coordinates[3],
            coordinates[4]
        )
    end
end

local function styleClassButton(button)
    local classToken = button.classToken
    local selected = selectedClassToken == classToken
    local hasChanges = addon.HasClassChanges(activeChannel, classToken)

    button.icon:SetAlpha((hasChanges or selected) and 1 or 0.3)
    if selected then
        button:SetBackdropBorderColor(1, 0.82, 0, 1)
        button:SetBackdropColor(0.15, 0.2, 0.3, 1)
    else
        button:SetBackdropBorderColor(0.28, 0.32, 0.4, 1)
        button:SetBackdropColor(0.05, 0.06, 0.08, 1)
    end
end

local function createClassButton(classId, className, classToken)
    local button = CreateFrame("Button", nil, frame, "BackdropTemplate")
    local offset = CLASS_ICON_START + ((classId - 1) * CLASS_ICON_STEP)
    button:SetSize(CLASS_ICON_SIZE + 4, CLASS_ICON_SIZE + 4)
    button:SetPoint("TOPLEFT", frame, "TOPLEFT", offset, -53)
    button:SetBackdrop({
        bgFile = "Interface/Tooltips/UI-Tooltip-Background",
        edgeFile = "Interface/Tooltips/UI-Tooltip-Border",
        edgeSize = 8,
    })
    button.classToken = classToken
    button.className = className
    button.icon = button:CreateTexture(nil, "ARTWORK")
    button.icon:SetSize(CLASS_ICON_SIZE, CLASS_ICON_SIZE)
    button.icon:SetPoint("CENTER")
    setClassIcon(button.icon, classToken)
    button:SetScript("OnClick", function()
        selectedClassToken = classToken
        addon.RefreshWindow()
    end)
    button:SetScript("OnEnter", function()
        GameTooltip:SetOwner(button, "ANCHOR_TOP")
        GameTooltip:SetText(className)
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function()
        GameTooltip:Hide()
    end)
    table.insert(classButtons, button)
end

for classId = 1, CLASS_COUNT do
    local className, classToken = GetClassInfo(classId)
    if classToken ~= nil then
        createClassButton(classId, className, classToken)
    end
end

local function hidePooledWidgets()
    for _, header in ipairs(headerPool) do
        header:Hide()
    end
    for _, note in ipairs(notePool) do
        note:Hide()
    end
    usedHeaders = 0
    usedNotes = 0
end

local function acquireHeader()
    usedHeaders = usedHeaders + 1
    local header = headerPool[usedHeaders]
    if header ~= nil then
        header:Show()
        return header
    end

    header = CreateFrame("Button", nil, content, "BackdropTemplate")
    header:SetSize(646, 32)
    header:SetBackdrop({
        bgFile = "Interface/Tooltips/UI-Tooltip-Background",
    })
    header:SetBackdropColor(0.09, 0.12, 0.17, 0.95)
    header.label = header:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontNormal"
    )
    header.label:SetPoint("LEFT", header, "LEFT", 12, 0)
    table.insert(headerPool, header)

    return header
end

local function acquireNote()
    usedNotes = usedNotes + 1
    local note = notePool[usedNotes]
    if note ~= nil then
        note:Show()
        return note
    end

    note = CreateFrame("Frame", nil, content)
    note:SetWidth(630)
    note.heading = note:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontNormal"
    )
    note.heading:SetPoint("TOPLEFT", note, "TOPLEFT", 6, -6)
    note.heading:SetWidth(618)
    note.heading:SetJustifyH("LEFT")
    note.meta = note:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontHighlightSmall"
    )
    note.meta:SetPoint("TOPLEFT", note.heading, "BOTTOMLEFT", 0, -4)
    note.meta:SetWidth(618)
    note.meta:SetJustifyH("LEFT")
    note.body = note:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontHighlight"
    )
    note.body:SetPoint("TOPLEFT", note.meta, "BOTTOMLEFT", 0, -7)
    note.body:SetWidth(618)
    note.body:SetJustifyH("LEFT")
    note.body:SetJustifyV("TOP")
    note.fallback = note:CreateFontString(
        nil,
        "OVERLAY",
        "GameFontDisableSmall"
    )
    note.fallback:SetPoint("TOPLEFT", note.body, "BOTTOMLEFT", 0, -4)
    note.fallback:SetTextColor(0.88, 0.68, 0.28, 1)
    table.insert(notePool, note)

    return note
end

local function setNoteContent(note, change)
    local localized, usedFallback = addon.GetLocalizedChange(change)
    local heading = localized.name
    if localized.specialization ~= ""
        and localized.specialization ~= "All"
    then
        heading = heading .. " — " .. localized.specialization
    end

    local metadata = { change.date }
    if change.patch ~= "" then
        table.insert(metadata, change.patch)
    end

    note.heading:SetText(heading)
    note.meta:SetText(table.concat(metadata, "  •  "))
    note.body:SetText("• " .. table.concat(localized.change, "\n• "))
    if usedFallback then
        note.fallback:SetText(addon.GetText("ENGLISH_FALLBACK"))
        note.fallback:Show()
    else
        note.fallback:SetText("")
        note.fallback:Hide()
    end

    local height = 54 + note.body:GetStringHeight()
    if usedFallback then
        height = height + 18
    end
    note:SetHeight(height)

    return height
end

local function restorePosition()
    frame:ClearAllPoints()
    local position = addon.db.window
    frame:SetPoint(
        position.point,
        UIParent,
        position.point,
        position.x,
        position.y
    )
end

function addon.RefreshWindow()
    if not frame:IsShown() then
        return
    end

    hidePooledWidgets()
    styleTab(tabs.live, activeChannel == "live")
    styleTab(tabs.ptr, activeChannel == "ptr")

    local actualClassToken, specializationId = addon.GetPlayerContext()
    playerClassToken = actualClassToken
    if selectedClassToken == nil then
        selectedClassToken = playerClassToken
    end

    for _, classButton in ipairs(classButtons) do
        styleClassButton(classButton)
    end

    local isPlayerClass = selectedClassToken == playerClassToken
    local showAllSpecializations = not isPlayerClass
    local sections = addon.GetSections(
        activeChannel,
        selectedClassToken,
        specializationId,
        showAllSpecializations
    )
    local y = -8

    if #sections == 0 then
        local note = acquireNote()
        note:ClearAllPoints()
        note:SetPoint("TOPLEFT", content, "TOPLEFT", 8, y)
        note.heading:SetText(addon.GetText("NO_CHANGES"))
        note.meta:SetText("")
        note.body:SetText("")
        note.fallback:Hide()
        note:SetHeight(42)
        y = y - 50
    end

    for _, section in ipairs(sections) do
        local collapseKey = table.concat({
            activeChannel,
            selectedClassToken,
            section.key,
        }, ":")
        if collapsed[collapseKey] == nil then
            collapsed[collapseKey] = not section.expanded
        end
        local isCollapsed = collapsed[collapseKey]
        local header = acquireHeader()
        header:ClearAllPoints()
        header:SetPoint("TOPLEFT", content, "TOPLEFT", 8, y)
        local marker = isCollapsed and "+  " or "−  "
        header.label:SetText(marker .. section.title)
        header:SetScript("OnClick", function()
            collapsed[collapseKey] = not collapsed[collapseKey]
            addon.RefreshWindow()
        end)
        y = y - 38

        if not isCollapsed then
            for _, change in ipairs(section.changes) do
                local note = acquireNote()
                note:ClearAllPoints()
                note:SetPoint("TOPLEFT", content, "TOPLEFT", 16, y)
                local noteHeight = setNoteContent(note, change)
                y = y - noteHeight - 10
            end
        end
    end

    content:SetHeight(math.max(1, -y + 8))
end

function addon.ShowWindow(channel)
    activeChannel = channel or "live"
    playerClassToken = addon.GetPlayerContext()
    selectedClassToken = playerClassToken
    restorePosition()
    frame:Show()
    addon.RefreshWindow()
end

function addon.HideWindow()
    frame:Hide()
end

frame:SetScript("OnMouseDown", function(self, button)
    if button == "LeftButton" then
        self:StartMoving()
    end
end)
frame:SetScript("OnMouseUp", function(self)
    self:StopMovingOrSizing()
    local point, _, _, x, y = self:GetPoint(1)
    addon.db.window.point = point
    addon.db.window.x = x
    addon.db.window.y = y
end)
frame:SetScript("OnHide", function()
    if addon.db == nil then
        return
    end

    local classToken = addon.GetPlayerContext()
    if classToken ~= nil then
        addon.MarkAllSeen(classToken)
    end
end)

addon.window = frame
