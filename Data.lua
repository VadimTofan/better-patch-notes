local _, addon = ...

local function addSection(sections, key, title, changes, expanded)
    if #changes == 0 then
        return
    end

    table.insert(sections, {
        key = key,
        title = title,
        changes = changes,
        expanded = expanded,
    })
end

function addon.GetLocalizedChange(change)
    local locale = GetLocale()
    local localized = change.localizations[locale]
    local english = change.localizations.enUS
    local usedFallback = localized == nil

    if locale == "enGB" then
        usedFallback = false
    end

    return localized or english, usedFallback
end

local function specializationTitle(changes)
    local firstChange = changes[1]
    if firstChange == nil then
        return addon.GetText("CLASS_CHANGES")
    end

    local localized = addon.GetLocalizedChange(firstChange)
    if localized.specialization == "" then
        return addon.GetText("CLASS_CHANGES")
    end

    return localized.specialization
end

function addon.HasClassChanges(channel, classToken)
    for _, change in ipairs(addon.PatchNotesData.changes) do
        if change.channel == channel
            and change.category == "Class"
            and change.classToken == classToken
        then
            return true
        end
    end

    return false
end

function addon.GetSections(
    channel,
    classToken,
    specializationId,
    allSpecializations
)
    local currentSpecialization = {}
    local classWide = {}
    local otherSpecializations = {}
    local allClassChanges = {}
    local dungeons = {}
    local raids = {}

    for _, change in ipairs(addon.PatchNotesData.changes) do
        if change.channel == channel then
            if change.category == "Class"
                and change.classToken == classToken
            then
                if allSpecializations then
                    table.insert(allClassChanges, change)
                elseif change.specializationId == specializationId then
                    table.insert(currentSpecialization, change)
                elseif change.specializationId == 0 then
                    table.insert(classWide, change)
                else
                    table.insert(otherSpecializations, change)
                end
            elseif change.category == "Dungeon" then
                table.insert(dungeons, change)
            elseif change.category == "Raid" then
                table.insert(raids, change)
            end
        end
    end

    local sections = {}
    if allSpecializations then
        addSection(
            sections,
            "all-specializations",
            addon.GetText("CLASS_CHANGES"),
            allClassChanges,
            true
        )
    else
        addSection(
            sections,
            "current-specialization",
            specializationTitle(currentSpecialization),
            currentSpecialization,
            true
        )
        addSection(
            sections,
            "class-wide",
            addon.GetText("CLASS_WIDE"),
            classWide,
            true
        )
        addSection(
            sections,
            "other-specializations",
            addon.GetText("OTHER_SPECIALIZATIONS"),
            otherSpecializations,
            false
        )
    end
    addSection(
        sections,
        "dungeons",
        addon.GetText("DUNGEON_CHANGES"),
        dungeons,
        true
    )
    addSection(
        sections,
        "raids",
        addon.GetText("RAID_CHANGES"),
        raids,
        true
    )

    return sections
end
