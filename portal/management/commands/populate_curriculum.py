from django.core.management.base import BaseCommand
from portal.models import Subject, ClassRoom, ClassRoomSubject

class Command(BaseCommand):
    help = 'Automatically populates subjects and classes according to school curriculum rules.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Setting up Future Leaders Private Academy curriculum...'))

        # 1. Define Subject Pools
        kg_base_subjects = [
            "Handwriting", "Letter work", "Social studies", "Health habits", 
            "Music", "Number work", "Computer", "Rhymes", "Science", 
            "Poem", "Phonetics", "Coloring"
        ]

        nursery_extras = ["Quantitative Reasoning", "Verbal Reasoning"]

        primary_base_subjects = [
            "Maths", "English", "Religious and National Values (RNV)", 
            "Basic Science", "Cultural and Creative Arts (CCA)", "History", 
            "Quantitative Aptitude Test", "Verbal Reasoning", "Vocation", 
            "Phonics", "Yoruba"
        ]

        # Combine all unique subjects to ensure they exist in the Subject table
        all_unique_subjects = set(kg_base_subjects + nursery_extras + primary_base_subjects + ["Pre-vocation", "Music"])
        
        subject_objs = {}
        for subj_name in all_unique_subjects:
            subj_obj, created = Subject.objects.get_or_create(name=subj_name)
            subject_objs[subj_name] = subj_obj

        self.stdout.write(self.style.SUCCESS(f'Successfully created/verified {len(subject_objs)} master subjects.'))

        # 2. Define Classes to Create (Skipping Primary 5 as requested)
        classes_config = [
            # Kindergarten
            {"name": "KG 1", "section": "KG", "level": 1, "type": "kg"},
            {"name": "KG 2", "section": "KG", "level": 2, "type": "kg"},
            
            # Nursery
            {"name": "Nursery 1", "section": "Nursery", "level": 1, "type": "nursery"},
            {"name": "Nursery 2", "section": "Nursery", "level": 2, "type": "nursery"},
            
            # Primary (1, 2, 3, 4, 6 - skipping 5)
            {"name": "Primary 1", "section": "Primary", "level": 1, "type": "primary"},
            {"name": "Primary 2", "section": "Primary", "level": 2, "type": "primary"},
            {"name": "Primary 3", "section": "Primary", "level": 3, "type": "primary"},
            {"name": "Primary 4", "section": "Primary", "level": 4, "type": "primary"},
            {"name": "Primary 6", "section": "Primary", "level": 6, "type": "primary"},
        ]

        for config in classes_config:
            classroom, created = ClassRoom.objects.get_or_create(
                name=config["name"],
                defaults={
                    "section": config["section"],
                    "level_number": config["level"]
                }
            )
            
            # Clear existing mapped subjects to avoid duplication if re-run
            ClassRoomSubject.objects.filter(class_room=classroom).delete()

            # Assign subjects based on tier rules
            assigned_subjects = []
            
            if config["type"] == "kg":
                assigned_subjects = kg_base_subjects
                
            elif config["type"] == "nursery":
                assigned_subjects = kg_base_subjects + nursery_extras
                
            elif config["type"] == "primary":
                assigned_subjects = list(primary_base_subjects)
                
                # Conditional Rules for Primary
                level = config["level"]
                
                # Pre-vocation is only for Primary 4 and 6
                if level in [4, 6]:
                    assigned_subjects.append("Pre-vocation")
                    
                # Music is only for Primary 3, 4, and 6
                if level in [3, 4, 6]:
                    assigned_subjects.append("Music")

            # Link subjects to the class
            for s_name in assigned_subjects:
                ClassRoomSubject.objects.create(
                    class_room=classroom,
                    subject=subject_objs[s_name]
                )

            action = "Created" if created else "Updated"
            self.stdout.write(f"-> {action} Class: {classroom.name} with {len(assigned_subjects)} subjects.")

        self.stdout.write(self.style.SUCCESS('✨ Curriculum architecture populated successfully!'))