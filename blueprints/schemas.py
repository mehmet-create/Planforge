from dataclasses import dataclass

@dataclass
class GenerateBlueprintDTO:
    project_id:      int
    organization_id: int
    acting_user_id:  int
    prompt:          str

    def __post_init__(self):
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("Prompt cannot be empty.")
        if len(self.prompt) > 4000:
            raise ValueError("Prompt cannot exceed 4000 characters.")


@dataclass
class DeleteBlueprintDTO:
    blueprint_uuid:  str
    acting_user_id:  int
    organization_id: int