import pkg_resources
import six
import six.moves.urllib.error
import six.moves.urllib.parse
import six.moves.urllib.request

from django.template import Context, Template

from xblock.core import XBlock
from xblock.fields import Integer, Scope, String, Dict
from xblock.fragment import Fragment
from xblockutils.studio_editable import StudioEditableXBlockMixin
from opaque_keys.edx.keys import CourseKey, UsageKey
from lms.djangoapps.courseware.courses import get_course_with_access
from django.contrib.auth.models import User
from submissions import api as submissions_api
from student.models import user_by_anonymous_id
from courseware.models import StudentModule
import json

# Make '_' a no-op so we can scrape strings
_ = lambda text: text

def reify(meth):
        """
        Decorator which caches value so it is only computed once.
        Keyword arguments:
        inst
        """
        def getter(inst):
            """
            Set value to meth name in dict and returns value.
            """
            value = meth(inst)
            inst.__dict__[meth.__name__] = value
            return value
        return property(getter)

class EolListGradeXBlock(StudioEditableXBlockMixin, XBlock):

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="Eol List Grade XBlock",
        scope=Scope.settings,
    )
    puntajemax = Integer(#float
        display_name='Puntaje Maximo',
        help='Entero que representa puntaje maximo',
        default=100,
        values={'min': 1},
        scope=Scope.settings,
    )
    comentario = Dict(
        help='comentarios otorgados',
        default={},
        scope=Scope.settings,
    )
    puntaje = Dict(
        help='puntaje otorgado',
        default={},
        scope=Scope.preferences,
    )
   
    #editable_fields = ('puntajemax', 'puntaje', 'comentario', 'display_name')

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    @reify
    def block_course_id(self):
        """
        Return the course_id of the block.
        """
        return six.text_type(self.course_id)

    @reify
    def block_id(self):
        """
        Return the usage_id of the block.
        """
        return six.text_type(self.scope_ids.usage_id)

    def is_course_staff(self):
        # pylint: disable=no-member
        """
         Check if user is course staff.
        """
        return getattr(self.xmodule_runtime, 'user_is_staff', False)

    def is_instructor(self):
        # pylint: disable=no-member
        """
        Check if user role is instructor.
        """
        return self.xmodule_runtime.get_user_role() == 'instructor'

    def show_staff_grading_interface(self):
        """
        Return if current user is staff and not in studio.
        """
        in_studio_preview = self.scope_ids.user_id is None
        return self.is_course_staff() and not in_studio_preview


    def get_submission(self, student_id=None):
        """
        Get student's most recent submission.
        """
        submissions = submissions_api.get_submissions(
            self.get_student_item_dict(student_id)
        )
        if submissions:
            # If I understand docs correctly, most recent submission should
            # be first
            return submissions[0]
    
    def get_student_item_dict(self, student_id=None):
        # pylint: disable=no-member
        """
        Returns dict required by the submissions app for creating and
        retrieving submissions for a particular student.
        """
        if student_id is None:
            student_id = self.xmodule_runtime.anonymous_student_id
            assert student_id != (
                'MOCK', "Forgot to call 'personalize' in test."
            )
        return {
            "student_id": student_id,
            "course_id": self.block_course_id,
            "item_id": self.block_id,
            "item_type": 'problem',
        }

    def get_score(self, student_id=None):
        """
        Return student's current score.
        """
        score = submissions_api.get_score(
            self.get_student_item_dict(student_id)
        )
        if score:
            return score['points_earned']

    def get_com(self, student_id, course_key, block_key):
        """
        Return student's comments
        """
        
        try:
            student_module = StudentModule.objects.get(
                student_id=student_id,
                course_id=self.course_id,
                module_state_key=self.location
                )
        except StudentModule.DoesNotExist:
            student_module = None

        if student_module:
            return json.loads(student_module.state)
        return {}

    def get_or_create_student_module(self, student_id):
        """
        Gets or creates a StudentModule for the given user for this block
        Returns:
            StudentModule: A StudentModule object
        """
        # pylint: disable=no-member
        student_module, created = StudentModule.objects.get_or_create(
            course_id=self.course_id,
            module_state_key=self.location,
            student_id=student_id,
            defaults={
                'state': '{}',
                'module_type': self.category,
            }
        )       
            
        return student_module

    def student_view(self, context=None):
        
        context = self.get_context()
        template = self.render_template('static/html/eollistgrade.html', context)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eollistgrade.css"))
        frag.add_javascript(self.resource_string("static/js/src/eollistgrade.js"))
        frag.initialize_js('EolListGradeXBlock')
        return frag

    def studio_view(self, context=None):
        aux = 'course-v1:mss+MSS001+2019_2'
        course_key = CourseKey.from_string(aux)
        #course = get_course_with_access(request.user, 'staff', course_key, depth=None)
        enrolled_students = User.objects.filter(
            courseenrollment__course_id=course_key
            #courseenrollment__is_active=1
        ).order_by('username').select_related("profile")

        lista_alumnos = enrolled_students
        context = {'lista_alumnos': lista_alumnos}
        template = self.render_template('static/html/eollistgrade.html', context)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eollistgrade.css"))
        frag.add_javascript(self.resource_string("static/js/src/eollistgrade.js"))
        frag.initialize_js('EolListGradeXBlock')
        return frag

    def get_context(self):
        aux = self.block_course_id
        course_key = CourseKey.from_string(aux)        
        #course = get_course_with_access(request.user, 'staff', course_key, depth=None)
        enrolled_students = User.objects.filter(
            courseenrollment__course_id=course_key
            #courseenrollment__is_active=1
        ).order_by('username').values('id', 'username')
        context = {'xblock': self}
        lista_alumnos = []
        if self.show_staff_grading_interface():
            for a in enrolled_students:
                p = self.get_score(a['id']) if self.get_score(a['id']) else ''
                state = self.get_com(a['id'], course_key, self.block_id)
                com=''
                if 'comment' in state:
                    com = state['comment']                
                lista_alumnos.append({'id': a['id'], 'username': a['username'], 'pun': p, 'com': com })

            context['lista_alumnos'] = lista_alumnos           
            context['category'] = type(self).__name__
        
            context['is_course_staff'] = True
        
        return context


    @XBlock.json_handler
    def savestudentanswers(self, data, suffix=''):
        user = user_by_anonymous_id(data.get('id'))
        student_module = self.get_or_create_student_module(data.get('id'))
        state = json.loads(student_module.state)
        score = int(data.get('puntaje'))
        state['comment'] = data.get('comentario')
        state['student_score'] = score
        state['score_max'] = data.get('puntajemax')
        student_module.state = json.dumps(state)
        student_module.save()

        student_item = {
            'student_id': data.get('id'),
            'course_id': self.block_course_id,            
            'item_id': self.block_id,
            'item_type': 'problem'
        }
        submission = self.get_submission(data.get('id'))
        if submission:
            submissions_api.set_score(submission['uuid'], score, data.get('puntajemax'))
        else:
            submission = submissions_api.create_submission(student_item, 'any answer')
            submissions_api.set_score(submission['uuid'], score, int(data.get('puntajemax')))

        return {'result': 'success', 'id': data.get('id')}

    @XBlock.json_handler
    def savestudentanswersall(self, data, suffix=''):        
        for fila in data.get('data'):           
            user = user_by_anonymous_id(fila[0])
            student_module = self.get_or_create_student_module(fila[0])
            state = json.loads(student_module.state)
            score = int(fila[1])
            state['comment'] = fila[2]
            state['student_score'] = score
            state['score_max'] = data.get('puntajemax')
            student_module.state = json.dumps(state)
            student_module.save()

            student_item = {
                'student_id': fila[0],
                'course_id': self.block_course_id,            
                'item_id': self.block_id,
                'item_type': 'problem'
            }
            submission = self.get_submission(fila[0])
            if submission:
                submissions_api.set_score(submission['uuid'], score, data.get('puntajemax'))
            else:
                submission = submissions_api.create_submission(student_item, 'any answer')
                submissions_api.set_score(submission['uuid'], score, int(data.get('puntajemax')))

        return {'result': 'success', 'id': '00'}


    def render_template(self, template_path, context):
        template_str = self.resource_string(template_path)
        template = Template(template_str)
        return template.render(Context(context))
    
        # workbench while developing your XBlock.
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("EolListGradeXBlock",
             """<eollistgrade/>
             """),
            ("Multiple EolListGradeXBlock",
             """<vertical_demo>
                <eollistgrade/>
                <eollistgrade/>
                <eollistgrade/>
                </vertical_demo>
             """),
        ]