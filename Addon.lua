local _, addon = ...

addon.name = "BetterPatchNotes"
addon.version = "0.2.3"

function addon.GetPlayerContext()
    local _, classToken = UnitClass("player")
    local specializationIndex = GetSpecialization()
    local specializationId = 0
    if specializationIndex ~= nil then
        specializationId = GetSpecializationInfo(specializationIndex) or 0
    end

    return classToken, specializationId
end
